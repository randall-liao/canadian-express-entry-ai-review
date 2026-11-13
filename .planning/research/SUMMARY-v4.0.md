# Project Research Summary

**Project:** PR Review Agents — Canadian PR Application Guide  
**Milestone:** v4.0 — CRS Profile ↔ Document Substantiation Auditor  
**Domain:** Local, PII-safe post-ITA Express Entry CRS claim substantiation against applicant documents  
**Researched:** 2026-07-05  
**Confidence:** MEDIUM-HIGH overall; HIGH for grounded CRS factor coverage and additive architecture, MEDIUM for extraction reliability until fixture validation passes

## Executive Summary

v4.0 is a post-ITA substantiation auditor, not another document checklist and not a CRS optimization engine. It answers: **does the applicant's local document set substantiate the CRS points that produced the ITA?** Expert implementation should model A11.2-style officer review: for every claimed CRS factor, verify document **presence**, extracted **value/threshold**, and corpus-grounded **admissibility**, then emit `SUBSTANTIATED`, `GAP`, `AT-RISK`, or `N/A` with cited rule predicates and private evidence pointers.

The recommended approach is additive: keep the shipped v3.x trust path frozen (`search` → `--cite` → grounding gate → JSON envelope), add a git-ignored candidate vault under `personal/`, store SQLite metadata plus content-addressed files on disk, quarantine extraction as `pending`, and require field-level user confirmation before any value can support a green verdict. Immigration-rule facts must come from a PII-free CRS rule registry generated and validated from the local authoritative corpus; applicant evidence must never enter `corpus/`, `.planning/`, public reports, or stdout.

The primary risks are privacy leakage, false confidence from OCR/extraction, stale or historical CRS rule selection, and over-claiming `SUBSTANTIATED` where semantic judgment is still required. Mitigate by building in this order: private vault/guardrails first, extraction + confirmation second, grounded rule registry and deterministic CRS math third, then modular auditors and private reporting. Extraction reliability is the only material MEDIUM-confidence area and must be proven with synthetic/adversarial fixtures before release.

## Key Findings

### Recommended Stack

Keep the current local Python/Poetry architecture, SQLite FTS5 corpus search, citation resolver, grounding gate, JSON envelope, `pydantic`, `platformdirs`, and PII separation. Add only the smallest local document stack needed for rendering, text/OCR fallback, structured extraction, and private vault storage.

**New stack additions and pinned/ranged versions:**
- **`pypdfium2` 5.11.0** — default local PDF-page renderer; prebuilt wheels, no Poppler install, permissive licensing, integrates with Pillow.
- **`Pillow` 12.3.0** — image loading/normalization/rendered-page handling and OCR handoff.
- **`pdfminer.six` 20260107** — first-tier born-digital PDF text extraction; use before OCR.
- **`pytesseract` 0.3.13** — optional local OCR fallback only, behind an OCR extra and a `tesseract --version`/language-data preflight.
- **`pydantic` 2.13.4** — typed CRS profile, extraction, evidence, verdict, and rule-registry models.
- **`platformdirs` 4.10.0** — packaged-install fallback for private data root while source checkouts default to ignored `personal/`.
- **`typer` 0.26.8** — additive CLI verbs (`vault`, `extract`, `confirm`, `crs-rules`, `crs-audit`) while preserving the existing envelope.
- **stdlib `sqlite3`** — candidate vault metadata; use files-on-disk for raw PDFs/images/rendered pages, not BLOBs.

**Explicitly do NOT add for v4.0:**
- No vector DBs, embeddings, semantic retrieval, or local RAG over applicant documents.
- No cloud OCR, cloud document AI, cloud LLM, or remote vision APIs; applicant documents stay local.
- No heavy ML OCR/layout stacks such as PaddleOCR/EasyOCR/docTR/large OpenCV pipelines.
- No default PyMuPDF unless the project explicitly accepts AGPL/commercial licensing; optional fallback only.
- No default `pdf2image`/Poppler dependency; optional fallback for users who already have Poppler.
- No pre-ITA CRS optimization or legal-advice engine.

### Verdict Semantics

| Verdict | Required meaning | Roadmap implication |
|---------|------------------|---------------------|
| `SUBSTANTIATED` | Required proof exists; evidence is `confirmed`/`corrected`; values meet the claimed threshold; admissibility/threshold rule is grounded and cited. | Never allow pending, low-confidence, stale, or semantically unresolved evidence to go green. |
| `GAP` | Required proof is missing, wrong, expired, ineligible, unconfirmed where a required predicate cannot be satisfied, or confirmed values are below the claimed threshold. | Recalculate this factor downward and show CRS delta/cutoff impact. |
| `AT-RISK` | Evidence exists but extraction confidence, format, policy edge case, semantic NOC/duties fit, staleness, or officer discretion prevents deterministic substantiation. | Show amber blocker, exact fix/confirmation needed, and rule citation; do not count as safe. |
| `N/A` | Factor not claimed or not applicable under spouse/accompanying status. | Keep in audit trail but collapse in UI. |

### Expected Features

**Must have for v4.0 launch:**
- Candidate vault for CRS profile, ITA round/cutoff, raw documents, extracted values, confirmations, audit runs, verdicts, and citations.
- Automated local extraction with mandatory field-level "confirm what I read"; extraction is the only non-grounded step.
- PII-free, precomputed CRS rule registry with citations/quotes validated by the existing corpus search and grounding gate.
- Four context-light auditor modules: core human capital, spouse/common-law, skill transferability, additional points.
- Full CRS factor coverage with factor cards showing claimed value, confirmed extracted value, substantiated points, score delta, private evidence pointer, and rule citation.
- Score-impact/cutoff guardrail: compare substantiated total to the ITA round cutoff without giving legal advice.
- Current-policy arranged-employment guard: current job-offer additional CRS points are 0 unless ITA-era corpus rules prove a legacy/exception case.

**Should have / differentiators:**
- Profile ↔ document mismatch matrix by factor and evidence record.
- CRS factor dependency graph, especially skill-transferability fan-out from education/language/work evidence.
- Predicate-level rule provenance: cite validity, issuer, threshold, accepted proof, cap, and effective-date predicates separately.
- Extraction confidence overlays and stale-confirmation indicators.
- Private report plus optional redacted shareable summary mode.

**Defer after v4.0 validation:**
- Legacy/physician arranged-employment research path for pre-2025-03-25 or public-policy edge cases.
- Live DLI/PGWP eligibility verifier for Canadian-study additional points.
- Work-duty semantic confidence scoring beyond deterministic required fields and manual review.
- MEC sidecar checks for FSW/FST/CEC eligibility; related but not identical to CRS substantiation.
- Document-specific fix checklist and lawyer/RCIC export packet.
- Pre-ITA CRS planning/optimization; likely v5+ and intentionally separate.

## Per-Factor CRS Feature Map

Each row must be implemented as **document(s) → value/threshold → admissibility rule → verdict**. All immigration-rule facts below must be encoded in the CRS rule registry with citations; structural comparison and arithmetic can be deterministic Python.

### A. Core Human Capital

| Factor | Document(s) | Value / threshold to compare | Admissibility rule / fail-closed guard |
|--------|-------------|------------------------------|----------------------------------------|
| Age | Passport/travel-document bio page; ITA date/round record | Age on ITA issue date maps to spouse/no-spouse CRS age table. Birthday after ITA that lowers points is not an automatic green/fail. | Passport identity/DOB must match profile; cite A11.2 birthday public-policy consideration and mark timing conflicts `AT-RISK`. |
| Education | Canadian credential proof, or foreign completed credential + ECA report/reference; translations if needed | Highest completed credential maps to claimed level; two-or-more requires at least one 3+ year credential. | Foreign education needs designated ECA/professional body, immigration-purpose report, completed Canadian-equivalency, within 5-year validity; Canadian credential must satisfy credential/institution rules. |
| First official language | Accepted language test result: CELPIP-G, IELTS General Training, PTE Core, TEF Canada, or TCF Canada | Four raw scores convert per ability to CLB/NCLC; apply first-language per-ability points and cap. | Accepted test/correct option, all four abilities, date-specific TEF table, less than 2 years old at relevant assessment/e-APR; low confidence or missing ability is never `SUBSTANTIATED`. |
| Second official language | Accepted test result for the language not designated first | Four abilities convert to CLB/NCLC; per-ability points with spouse/no-spouse cap. | Same accepted-test, validity, conversion, and disability-averaging rules; enforce correct language role. |
| Canadian work experience | Employer reference letters; optional T4/NOA/status/work permit support; NOC 2021 corpus | Sum eligible full-time/equivalent Canadian work within 10 years; map to claimed years/points. | Paid TEER 0-3 work, authorized Canadian work, not excluded full-time-study/self-employment periods, 30h/week cap, duties/NOC evidence; semantic NOC fit defaults `AT-RISK` unless manually resolved. |

### B. Spouse / Common-Law Factors

Applies only when there is an accompanying spouse/common-law partner who is not a Canadian citizen or permanent resident. Otherwise score the principal applicant under the no-spouse mode and mark spouse rows `N/A`.

| Factor | Document(s) | Value / threshold to compare | Admissibility rule / fail-closed guard |
|--------|-------------|------------------------------|----------------------------------------|
| Spouse education | Spouse Canadian credential, or spouse foreign completed credential + ECA; relationship proof; translations | Highest spouse education maps to spouse education table. | Same ECA/Canadian-credential rules as principal; evidence owner must be spouse and relationship/accompanying status must be confirmed. |
| Spouse language | Spouse accepted first-official-language test | Four abilities convert to CLB/NCLC; per-ability table capped at 20. | Accepted test, correct option, all four abilities, less than 2 years old, correct owner/language role. |
| Spouse Canadian work | Spouse Canadian employer reference letters plus support/status docs where needed | Eligible Canadian work years map to spouse work table. | Same Canadian-work admissibility rules as principal; owner separation is mandatory. |

### C. Skill Transferability

These factors recombine already-substantiated core evidence. They require explicit cap logic: education combinations max 50, foreign-work combinations max 50, total skill-transferability max 100.

| Factor | Document(s) | Value / threshold to compare | Admissibility rule / fail-closed guard |
|--------|-------------|------------------------------|----------------------------------------|
| Education × first official language | Principal education/ECA + first-language test | Post-secondary or higher + CLB/NCLC 7+ in all abilities, with CLB 9+ all abilities unlocking higher tiers; higher education group can reach 50. | Both component factors must be admissible and confirmed; use first official language only; one ability below threshold breaks the combination. |
| Education × Canadian work | Principal education/ECA + Canadian work evidence | Post-secondary/higher education combined with 1 year or 2+ years Canadian work maps to 13/25/50 tiers. | Component factors must be independently substantiated; enforce education-combination cap. |
| Foreign work × first official language | Foreign work letters/support + first-language test | 1-2 or 3+ years foreign skilled work combined with CLB/NCLC 7+ all or 9+ all maps to 13/25/50 tiers. | Foreign work must be paid, outside Canada, within 10 years, TEER 0-3, full-time/equivalent, with NOC/duties evidence; distinguish CRS thresholds from FSW MEC continuity. |
| Foreign work × Canadian work | Foreign work evidence + Canadian work evidence | 1-2 or 3+ foreign years combined with 1 or 2+ Canadian years maps to 13/25/50 tiers. | Component work factors must be substantiated; avoid overlapping/double-counted hours and enforce foreign-work-combination cap. |
| Certificate of qualification × first official language | Canadian federal/provincial/territorial trade certificate + first-language test | Valid certificate + CLB/NCLC 5+ all abilities yields lower tier; CLB/NCLC 7+ all yields 50. | Certificate must be valid at ITA/e-APR, issued by competent authority, for eligible trade; not apprenticeship/prequalification; language proof independently valid. |

### D. Additional Points

| Factor | Document(s) | Value / threshold to compare | Admissibility rule / fail-closed guard |
|--------|-------------|------------------------------|----------------------------------------|
| Provincial/territorial nomination | Nomination certificate / Express Entry nomination acceptance or profile-system evidence | 600 points only if eligible nomination is named, verified/accepted, and not revoked/expired/declined. | Add a "profile system evidence" type; cite MI/PNP rules and require status evidence. |
| Qualifying job offer / arranged employment | For current CRS: no document can substantiate non-zero additional job-offer CRS points under current rule; for eligibility only, offer/LMIA/work permit evidence may matter. | Current additional CRS points = 0. Legacy 50/200 claims are `AT-RISK` until ITA-era MI proves applicability. | Separate "valid offer for program eligibility" from "CRS additional points"; current job-offer points removed as of 2025-03-25 per corpus. |
| Canadian post-secondary study | Canadian credential/proof of studies, DLI, transcripts, program length/full-time/physical-presence evidence | Eligible 1-2 year credential = 15; eligible 3+ year/Master's/professional/doctoral = 30; secondary = 0. | Must satisfy Canadian institution/location/program/length, physical presence, distance/ESL/scholarship and COVID-era exception rules; live DLI/PGWP status may need later verifier. |
| Strong French-language skills | TEF Canada/TCF Canada French test; English test if claiming larger total | French NCLC 7+ all abilities yields 25; plus English CLB 5+ all abilities yields total 50. | Accepted tests, correct conversion/date-specific TEF table, less than 2 years old, all four abilities. |
| Sibling in Canada | Relationship proof, sibling citizenship/PR proof, current residence proof | 15 points if applicant or accompanying spouse has sibling age 18+, citizen/PR, living in Canada. | Relationship chain, status proof, and recent residence evidence required; stale/ambiguous residence or step-sibling relationship issues are `AT-RISK`. |

## Architecture Approach

The architecture is explicitly additive. Do not rebuild retrieval, citation resolution, grounding, rendering contracts, or the JSON envelope. Add a private candidate layer beside the existing public corpus layer:

1. **Shared path resolver (`crawler/paths.py`)** — resolve `personal/` or platformdirs fallback; every private write must pass containment checks and reject symlink/`..` escapes.
2. **Candidate vault (`crawler/vault.py`)** — SQLite owns profile factors, document metadata, extraction runs, extracted values, confirmation state, evidence links, audit runs, and verdict records. Raw files and rendered pages are content-addressed files on disk under `personal/candidates/<candidate-id>/`.
3. **Document extraction (`crawler/extraction.py`)** — `pdfminer.six` text first, `pypdfium2` render always, `Pillow` image normalization, optional local Tesseract for scans. Writes only `pending` values and vault-local artifacts.
4. **Confirmation checkpoint** — field-level confirm/correct/reject; auditors may query only `confirmed`/`corrected` evidence. Re-confirm when file hash, parser version, profile claim, or rule registry version changes.
5. **CRS rule registry (`crawler/data/crs_rules/*.yaml`, `crawler/crs_rules.py`)** — public PII-free cited table by factor group. Each row has query/selector/source family, machine check, citation ID, verbatim quote, volatility/staleness metadata, and conformance tests.
6. **Deterministic CRS logic (`crawler/crs_audit.py`)** — joins confirmed evidence to grounded rule rows; performs date math, CLB conversion, duration aggregation, spouse mode, caps, and cutoff comparison in tested Python.
7. **Auditor agent pack (`skills/crs-auditors/`)** — thin Markdown specs for core, spouse, skill transferability, and additional points; they reuse existing search/`--cite`/grounding-gate/JSON-envelope primitives.
8. **Private output renderer** — stdout stays PII-light; full reports and JSON live only under the candidate vault output directory.

**Critical invariant:** `corpus/index.db` is authoritative, PII-free, and citeable; `personal/candidates/<id>/vault.sqlite` is private, evidence-bearing, and never citeable as authority. Use `citation_id` only for corpus rules and `evidence_id` only for candidate evidence.

## Critical Pitfalls

| Build area | Pitfall | Prevention |
|------------|---------|------------|
| Vault | PII leaks through raw PDFs, rendered images, OCR text, vault DB/WAL files, logs, or reports. | Put every artifact under ignored `personal/`; path-guard writes; extend publish-safe/gitleaks tests; keep stdout/error messages PII-light. |
| Vault | Candidate evidence is indexed into the authoritative corpus or treated as a citation. | Enforce two stores; candidate text never enters `corpus/`; separate `evidence_id` from `citation_id`. |
| Vault | Stale confirmations survive document/profile/rule changes. | Tie confirmations to source hash, page/crop hash, parser version, profile version, and registry version; mark stale and block green verdicts. |
| Extraction/confirmation | Silent OCR/table/date/CLB/NOC misreads become grounded-looking false confidence. | Extraction starts `pending`; require field-level confirmation; low-quality/ambiguous/unconfirmed values can only yield `GAP` or `AT-RISK`. |
| Extraction/confirmation | Confirmation is a rubber stamp. | Show raw value, normalized value, page/crop, affected factor, profile claim, and rule consequence per field; allow correct/reject/wrong-person/split-document. |
| Extraction/confirmation | Dependency friction or scan quality failures are invisible. | Add `doctor`/preflight; render all pages; detect scanned/rotated/password-protected/low-text documents; mark quality states explicitly. |
| CRS registry | Volatile CRS rules are hard-coded in agent prose. | Registry rows must resolve through corpus search/`--cite` and pass grounding; static checks should reject inlined volatile thresholds. |
| CRS registry | Historical/adjacent chunks pass the gate but ground the wrong rule. | Source-family allowlists/disallowlists, marker selection, retrieve-what-you-cite tests, crawl-date/source URL in reports. |
| CRS registry / audit logic | CRS math misses spouse mode, per-ability language, transferability caps, or current job-offer repeal. | Deterministic tested CRS module; golden boundary fixtures for CLB 8/9, spouse/no-spouse, caps, and job-offer policy. |
| Auditor/report | `SUBSTANTIATED` overclaims legal certainty or semantic NOC duty fit. | Define green narrowly; mark semantic review and discretion as `AT-RISK`; include not-legal-advice framing. |
| Auditor/report | Full private report is written to tracked paths or PII appears in `claims[]`. | Full report only under vault; `claims[]` are generic/corpus-cited; private values stay in vault-only basis/report sections. |

## Implications for Roadmap

Based on the combined research, the roadmap should be staged around trust boundaries, not UI convenience.

### Phase 1: Candidate Vault + PII Guardrails

**Rationale:** No real document can be safely rendered or imported until the private storage boundary exists.  
**Delivers:** shared personal path resolver, candidate ID rules, SQLite schema/migrations, content-addressed file storage, factor IDs, profile/ITA-round import, private output path, publish-safety/gitleaks regression tests.  
**Addresses:** candidate vault, CRS claim intake, PII separation, stale-confirmation versioning foundation.  
**Avoids:** PII leakage, vault/corpus boundary blur, stale evidence, tracked private reports.  
**Research flag:** Low. Standard local SQLite/filesystem pattern; validate current `.gitignore`/publish-safe coverage.

### Phase 2: Extraction + Field-Level Confirmation

**Rationale:** Value matching is the new capability, and extraction is the only non-grounded step. It must be quarantined before auditors exist.  
**Delivers:** PDF/image ingest, `pdfminer.six` text extraction, `pypdfium2` rendering, `Pillow` image handling, optional Tesseract OCR extra, `doctor` preflight, page-count coverage, `pending` extracted values, field-level confirm/correct/reject workflow.  
**Addresses:** automated reading, confirmation checkpoint, extraction confidence overlays, raw/rendered/text artifact storage.  
**Avoids:** silent misreads, rubber-stamp confirmation, dependency friction, low-quality scans producing green verdicts.  
**Research flag:** High. Extraction reliability is MEDIUM and needs synthetic/adversarial fixtures per document type before claiming automation.

### Phase 3: Grounded CRS Rule Registry + Deterministic CRS Logic

**Rationale:** Auditors must consume cited rules; they must not write their own CRS tables. This phase turns the corpus into validated, PII-free, machine-readable predicates.  
**Delivers:** rule YAML by four factor groups, query/selector/source-family specs, citation/quote validation via existing gate, CLB/NCLC conversions, validity windows, accepted issuers/tests, work definitions, caps, spouse mode, current arranged-employment guard, stale-source warnings.  
**Addresses:** all CRS rule facts, score/cutoff formulas, policy-change handling, source provenance.  
**Avoids:** hard-coded volatile rules, historical chunk selection, CRS cap/math errors, obsolete job-offer points.  
**Research flag:** High for arranged-employment legacy/physician edge cases and Canadian-study DLI/PGWP status. Medium for NOC/duty source-family selection. Standard for straightforward tables once citations are selected.

### Phase 4: Auditor Vertical Slice + Private Factor Cards

**Rationale:** Prove the full loop before fanning out: confirmed evidence + grounded rule rows + deterministic comparator + grounding gate + private output. Start with language or education because they have crisp thresholds and high user value.  
**Delivers:** one end-to-end factor group/slice with `SUBSTANTIATED`/`GAP`/`AT-RISK`, PII-light envelope, private report under vault, evidence pointers, rule citations, score delta, and negative tests for pending/low-confidence/stale values.  
**Addresses:** factor-card report, verdict semantics, fail-closed output contract.  
**Avoids:** over-claiming, PII in `claims[]`, partial grounded output on gate failure.  
**Research flag:** Medium. Patterns are known; the slice should reveal schema/report gaps.

### Phase 5: Full Modular Auditor Pack

**Rationale:** After the slice proves the contract, fan out along IRCC's factor grid while keeping context small. Skill transferability should consume already-proven core values; additional points should receive extra policy attention.  
**Delivers:** four auditor modules covering core human capital, spouse/common-law, skill transferability, and additional points; multi-document aggregation; factor dependency graph; substantiated CRS total and ITA cutoff comparison.  
**Addresses:** full CRS factor coverage, profile ↔ document mismatch matrix, transferability caps/fan-out, score-impact guardrail.  
**Avoids:** single-document-only checks, spouse/principal ownership mixups, work interval overlap errors, job-offer policy trap.  
**Research flag:** High for work-duty/NOC semantic limits and additional-points edge cases; standard for language/ECA tables after registry is validated.

### Phase 6: Conformance, Safety Hardening, and Release Docs

**Rationale:** The product promise is trust. Release only after fixture, grounding, and privacy gates prove fail-closed behavior.  
**Delivers:** synthetic fixture corpus, adversarial extraction cases, rule-registry retrieve-what-you-cite tests, no-PII stdout tests, non-vault output refusal tests, stale-invalidation tests, docs that frame the report as substantiation screening not legal advice.  
**Addresses:** publish readiness, user install experience, confidence communication.  
**Avoids:** "looks done but isn't" failures: unconfirmed green verdicts, private report leaks, stale rules, and semantic overreach.  
**Research flag:** Low-Medium. Mostly engineering hardening; add targeted research only if fixtures expose extraction/library limits.

### Phase Ordering Rationale

- The **vault** is first because it is the privacy perimeter and the data model for factor/evidence ownership.
- **Extraction/confirmation** follows because auditors need confirmed values, but extraction output must not be trusted by default.
- The **CRS rule registry** can run partly in parallel after Phase 1, but it must land before auditor implementation to prevent hard-coded rules.
- **Auditors** come last because they are deterministic joins over two prerequisites: confirmed evidence and grounded rule rows.
- **Full reporting and cutoff comparison** should wait until factor ledgers are complete; a total score without factor-level proof hides the exact mismatch risk.

### MVP vs Later Split

**MVP v4.0:**
1. Candidate vault under ignored `personal/` with SQLite metadata and content-addressed files.
2. Local extraction + field confirmation for language, ECA/education, passport/age, employment letters, certificate, nomination, job offer, Canadian study, sibling/relationship evidence.
3. CRS rule registry covering all factor IDs and thresholds from current corpus.
4. Four modular auditors with factor cards and score/cutoff impact.
5. Current arranged-employment guard: non-zero job-offer CRS claim is `AT-RISK`/0 unless ITA-era rule proves otherwise.
6. Safety/conformance suite proving no pending evidence can be `SUBSTANTIATED` and no PII leaves the vault.

**Later v4.0.x / v5+:**
- Legacy arranged-employment/physician-policy resolver.
- Live DLI/PGWP program eligibility lookup.
- Enhanced NOC duty semantic review workflow.
- MEC sidecar checks.
- Document-specific fix checklist.
- Redacted review/export packet.
- Pre-ITA optimization product.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Versions/APIs verified and fit the current Python stack. Extraction reliability across real PDFs/scans/letters is MEDIUM until fixture-backed. |
| Features | HIGH-MEDIUM | CRS factor grid, document mappings, point thresholds, validity windows, and A11.2 model are HIGH from local authoritative corpus; edge cases are MEDIUM. |
| Architecture | HIGH-MEDIUM | Reuse of shipped search/`--cite`/grounding/envelope primitives and `personal/` boundary is HIGH; extraction library choice and UX details are MEDIUM. |
| Pitfalls | HIGH-MEDIUM | PII, grounding, volatile-rule, and overclaiming pitfalls are HIGH confidence; OCR/rendering/dependency behavior is MEDIUM pending fixtures. |

**Overall confidence:** MEDIUM-HIGH. The design is strong and aligned with existing project invariants; the release risk is concentrated in extraction/confirmation reliability and a few volatile CRS rule edges.

### Gaps to Address

- **Extraction fixture validation:** Build synthetic/adversarial PDFs/images for language score boundaries, date ambiguity, multi-page letters, scanned/rotated documents, old NOC codes, and spouse/principal ownership.
- **Arranged-employment legacy cases:** Resolve ITA-era MI and physician/public-policy wording before ever awarding non-zero job-offer CRS points.
- **Canadian-study live eligibility:** Determine whether static corpus is enough or a live DLI/PGWP verifier is required for program/institution status.
- **NOC duty fit:** Do not use embeddings/cloud ML. Use deterministic required fields and manual/`AT-RISK` workflow for semantic duty matching.
- **Source freshness:** Registry must surface crawl date, source family, and stale/changed-rule warnings.
- **Confirmation UX:** Field-level confirmation is a trust boundary, not polish; plan it as a required workflow.

## Sources

### Primary (HIGH confidence)
- `.planning/research/STACK-v4.0.md` — local extraction/vault stack, versions, and explicit non-additions.
- `.planning/research/FEATURES-v4.0.md` — CRS factor map, verdict semantics, MVP/later split, source list.
- `.planning/research/ARCHITECTURE-v4.0.md` — additive vault/extraction/registry/auditor architecture and build order.
- `.planning/research/PITFALLS-v4.0.md` — trust-boundary, PII, grounding, CRS math, and extraction pitfalls mapped to phases.
- `.planning/notes/crs-claim-substantiation-auditor.md` — concept, locked decisions, four-module split, local vault, automated extraction caveat.
- Local authoritative corpus cited by researchers: Ministerial Instructions/current CRS criteria, Express Entry A11.2 PDIs, completeness-check PDI, language-test guidance/equivalency charts, ECA guidance, job-offer guidance, CRS criteria pages, documents/apply guidance, and NOC 2021 files.
- Existing project primitives: `crawler/CONTRACT.md`, `crawler/grounding.py`, `crawler/searchindex.py`, `skills/document-agents/_contract.md`, `scripts/check_publish_safe.py`, `.gitignore`.

### Secondary (MEDIUM confidence)
- PyPI and official/library docs verified by stack research for `pypdfium2`, `Pillow`, `pdfminer.six`, `pytesseract`, PyMuPDF, `pdf2image`, `platformdirs`, `sqlite-utils`, `pydantic`, and `typer`.
- Engineering experience around PDF rendering/OCR/native dependencies, scan quality, and multi-page document extraction; must be validated by v4.0 fixtures.

### Tertiary (LOW confidence)
- None used as authority. Third-party CRS tables, cloud document AI docs, vectors/embedding approaches, and legal-advice content are out of scope and must not ground implementation.

---
*Research completed: 2026-07-05*  
*Ready for roadmap: yes*
