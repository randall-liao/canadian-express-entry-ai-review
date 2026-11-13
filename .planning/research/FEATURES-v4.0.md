# Feature Research

**Domain:** Post-ITA Express Entry CRS profile ↔ e-APR document substantiation auditor  
**Researched:** 2026-07-05  
**Confidence:** HIGH for the CRS factor grid, core document mappings, point thresholds, validity windows, and e-APR/A11.2 consequence model because they are grounded in the local authoritative corpus (IRCC guidance, Ministerial Instructions, PDIs, NOC 2021). MEDIUM for edge cases that require phase-time corpus refresh or extra source resolution, especially legacy/physician arranged-employment treatment and live DLI/PGWP eligibility lookup.

## Context for this Research

v4.0 is not another document checklist milestone. v3.0/v3.1 already answer "which documents do I need?" and provide 22 grounded document agents. v4.0 answers a stricter post-ITA question: **does the document set substantiate the CRS points that produced the ITA?**

The auditor should model what the A11.2 review is trying to protect: at e-APR, officers compare the profile/e-APR claims against supporting documents, recalculate whether the applicant still possesses the qualifications behind the CRS score, and refuse if the recalculated score falls below the lowest-ranked candidate invited in that round. This is **substantiation**, not pre-ITA score optimization.

Every factor verdict must perform three checks:

1. **Presence** — the right proof type exists in the local candidate vault.
2. **Value** — extracted values in the document meet the exact CRS threshold claimed.
3. **Admissibility** — the proof is an IRCC-accepted kind of evidence, within validity/recency windows, from an accepted issuer/body, and in an accepted format.

Grounding boundary: all immigration-rule facts below must be cited from the corpus at implementation time. Structural logic such as comparing extracted values to claimed values, summing date ranges, applying caps, and routing factors to modules can be tested without a citation, but the formula/threshold being applied still needs a citation.

## Verdict Semantics

| Verdict | Meaning | Typical examples | UX action |
|---------|---------|------------------|-----------|
| `SUBSTANTIATED` | Required proof is present; extracted values meet or exceed the claimed threshold; the document is admissible under corpus-grounded rules. If a document appears to support more than claimed, mark substantiated for the claim and show an informational mismatch note, not score advice. | IELTS General result is unexpired at ITA/e-APR and maps to claimed CLB; ECA is from WES for immigration and maps to claimed Master's; reference letters add up to claimed Canadian-work years. | Green factor card with claimed value, extracted value, document link, and rule citation. |
| `GAP` | Proof is missing, the wrong proof type, expired/ineligible, or extracted values are below the claimed threshold. This factor should be removed or reduced in the auditor's recalculated CRS. | Language test expired before e-APR; ECA says "one year of undergraduate study" instead of completed credential; reference letter lacks dates/hours/duties; current rule gives 0 job-offer CRS points. | Red factor card with missing/failed predicate and CRS delta. |
| `AT-RISK` | Proof may be present, but acceptance depends on officer discretion, ambiguous extraction, policy edge cases, weak format, or near-expiry timing. Do not count as safe until resolved/confirmed. | OCR confidence low; employment letter has duties but no salary/hours; sibling residence proof older than 6 months; birthday after ITA invokes public-policy consideration; job-offer physician/legacy exception requires deeper rule lookup. | Amber factor card, "what to fix", cite the rule, and require user confirmation or extra document. |
| `N/A` | Factor does not apply or was not claimed. | No accompanying spouse; no sibling claim; no Canadian-study claim. | Collapsed neutral row; keep audit trail. |

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **CRS claim intake / candidate vault schema** | The auditor needs the ITA-time CRS breakdown, e-APR-time profile values, round cutoff, ITA date, spouse/accompanying status, and local document pointers. | HIGH | Extend the local git-ignored privacy pattern. Store raw docs, extracted fields, user confirmations, factor verdicts, and citations outside repo/corpus DB. |
| **Automated extraction + confirm-what-I-read checkpoint** | The user chose automated document reading, but extraction is the one non-grounded trust surface. | HIGH | Render PDFs/scans to images and text; extract dates, scores, credential levels, NOC, duties, hours, salary, issuer, certificate numbers; require confirmation before substantiation. |
| **Grounded CRS rule registry** | The same rule thresholds are reused across factors and must be citable. | HIGH | Registry owns point tables, validity windows, accepted issuers/tests, NOC/TEER requirements, skill-transferability caps, and policy effective dates. No hard-coded prompt-only rules. |
| **Four context-light auditor modules** | The full grid is too broad for one prompt; the concept locks the split to IRCC's CRS categories. | MEDIUM | Modules: core human capital; spouse/common-law; skill transferability; additional points. Each emits factor-level `SUBSTANTIATED` / `GAP` / `AT-RISK`. |
| **Full CRS factor coverage** | Missing any factor can hide a score-drop risk. | HIGH | Cover all current factors plus the repealed arranged-employment factor as a policy-aware 0/current or legacy/edge-case row. |
| **CRS recalculation for substantiation only** | The report must quantify whether gaps could drop the applicant below the round cutoff. | MEDIUM | Recalculate only from confirmed evidence and corpus-grounded formulas. Do not provide pre-ITA optimization suggestions. |
| **Cited factor cards** | The core product promise is grounded, cited guidance. | MEDIUM | Each card shows: claimed points, substantiated points, missing predicates, evidence docs, citation IDs, extraction confidence, and CRS delta. |
| **Existing document-agent reuse** | v3.1 already has document-specific rule agents; v4.0 should not duplicate their knowledge. | MEDIUM | Reuse `language-test`, `eca`, `employment-reference-letter`, `proof-of-studies`, `certificate-of-qualification`, `job-offer`, `passport`, `marriage/common-law`, `relative-in-canada`, and `translation` agents. |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Profile ↔ document mismatch matrix** | Shows exactly where the profile claim and document evidence diverge before submission. | MEDIUM | Example: profile claims CLB 9 all abilities, extracted IELTS listening maps to CLB 8. |
| **Score-impact and cutoff guardrail** | Turns factor gaps into "safe / below cutoff / unknown" without giving legal advice. | MEDIUM | Needs ITA round cutoff and MI-in-force-at-ITA snapshot. |
| **Policy-change-aware arranged-employment handling** | Prevents stale 50/200 job-offer points from being treated as current CRS points. | HIGH | Current corpus says job-offer CRS points removed March 25, 2025; legacy/physician wording needs explicit amber treatment unless the ITA-era MI proves points apply. |
| **Rule provenance by predicate** | Users trust the audit because each failed predicate has a cited rule. | MEDIUM | Cite not just the page, but the exact predicate: validity, issuer, point threshold, accepted proof, or cap. |
| **CRS factor graph** | Skill transferability points are combinations; a single missing ECA/language/work proof can break multiple factors. | HIGH | Show dependency fan-out so fixing one document explains multiple changed verdicts. |
| **Extraction confidence overlays** | Separates "IRCC rule says no" from "the system may have misread your document." | MEDIUM | Low-confidence extraction should produce `AT-RISK`, never `SUBSTANTIATED`. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Pre-ITA CRS optimization** | Users want a higher score. | Explicitly out of scope; changes product from substantiation to immigration strategy. | Only recalculate the score that is already claimed for ITA/e-APR safety. |
| **Silent OCR trust** | Fully automated feels convenient. | A misread score/date can create false confidence. | Mandatory extracted-value review before any green verdict. |
| **Treating checklist presence as substantiation** | Easier to implement. | "Uploaded a language result" is not the same as "unexpired accepted test mapping to claimed CLB." | Presence/value/admissibility predicates per factor. |
| **Awarding current arranged-employment CRS points** | Many older guides still mention 50/200 points. | Current corpus marks the CRS additional factor repealed/removing job-offer points as of March 25, 2025. | Current score = 0 unless an ITA-era/legacy corpus rule proves otherwise; keep job-offer validation for program eligibility only. |
| **Counting work by job title only** | Titles are easy to extract. | IRCC/NOC requires lead statement and substantial main duties, including essential duties; hours, dates, pay, and NOC TEER matter. | Require reference-letter fields and NOC duty matching. |
| **Hard-coding CRS tables in prompts** | Fast initial implementation. | Tables and policy can change; stale prompts break the product's grounding guarantee. | Rule registry generated/verified from corpus chunks with crawl date and citation IDs. |
| **Third-party CRS tables as authority** | They are easy to find. | Project source authority is IRCC/IRPA/IRPR/PDI/StatCan corpus only. | Use third-party only as discovery hints, never as cited rules. |
| **Legal advice / "will I be approved?"** | Users want certainty. | Unauthorized advice and overclaiming; officers retain discretion on some evidence. | Report documented substantiation status and recommend licensed advice for judgment calls. |

## Common Rule Primitives the Registry Must Encode

### Source-of-Truth Split

| Rule type | Must be corpus-grounded | Structural/test logic |
|-----------|-------------------------|-----------------------|
| CRS point grids, caps, factor categories | Yes — Ministerial Instructions / CRS criteria. | Apply the cited grid to extracted values. |
| Accepted tests, ECA bodies, job-offer/PNP/certificate eligibility | Yes — IRCC guidance/PDI/MI. | Match issuer/body/test name from extracted doc to accepted list. |
| Validity windows | Yes — language 2 years, ECA 5 years, certificate validity at ITA/e-APR, sibling residence recency, etc. | Compare document dates to ITA date and planned/actual e-APR submission date. |
| NOC/TEER and duties | Yes — MI + StatCan NOC corpus. | Map claimed NOC to TEER; compare duties text to lead statement/main duties using deterministic markers where possible. |
| Score delta / cutoff | Formula/cutoff must be cited from MI/round source. | Sum substantiated points, enforce caps, compare to lowest-ranked invited score. |

### Accepted Language Tests and Raw Score Conversion

Accepted test documents: **CELPIP-General**, **IELTS General Training**, **PTE Core**, **TEF Canada**, and **TCF Canada**. IELTS One Skill Retake is not accepted for Express Entry in the current language guidance; TOEFL Essentials appears in designated-testing context as not currently accepted by IRCC. The language result must show all four abilities and be less than 2 years old at both profile/ITA-relevant assessment and e-APR submission. For TEF Canada, the registry must branch by test date because the corpus has multiple equivalency tables; the compact table below shows the current post-December-10-2023 TEF scale.

Ability order below is **Reading / Writing / Listening / Speaking**.

| Benchmark | CELPIP-G | IELTS General Training | PTE Core | TEF Canada, after 2023-12-10 | TCF Canada |
|-----------|----------|------------------------|----------|------------------------------|------------|
| CLB/NCLC 10 | 10 / 10 / 10 / 10 | 8.0 / 7.5 / 8.5 / 7.5 | 88-90 / 90 / 89-90 / 89-90 | 546-699 / 558-699 / 546-699 / 556-699 | 549-699 / 16-20 / 549-699 / 16-20 |
| CLB/NCLC 9 | 9 / 9 / 9 / 9 | 7.0 / 7.0 / 8.0 / 7.0 | 78-87 / 88-89 / 82-88 / 84-88 | 503-545 / 512-557 / 503-545 / 518-555 | 524-548 / 14-15 / 523-548 / 14-15 |
| CLB/NCLC 8 | 8 / 8 / 8 / 8 | 6.5 / 6.5 / 7.5 / 6.5 | 69-77 / 79-87 / 71-81 / 76-83 | 462-502 / 472-511 / 462-502 / 494-517 | 499-523 / 12-13 / 503-522 / 12-13 |
| CLB/NCLC 7 | 7 / 7 / 7 / 7 | 6.0 / 6.0 / 6.0 / 6.0 | 60-68 / 69-78 / 60-70 / 68-75 | 434-461 / 428-471 / 434-461 / 456-493 | 453-498 / 10-11 / 458-502 / 10-11 |
| CLB/NCLC 6 | 6 / 6 / 6 / 6 | 5.0 / 5.5 / 5.5 / 5.5 | 51-59 / 60-68 / 50-59 / 59-67 | 393-433 / 379-427 / 393-433 / 422-455 | 406-452 / 7-9 / 398-457 / 7-9 |
| CLB/NCLC 5 | 5 / 5 / 5 / 5 | 4.0 / 5.0 / 5.0 / 5.0 | 42-50 / 51-59 / 39-49 / 51-58 | 352-392 / 330-378 / 352-392 / 387-421 | 375-405 / 6 / 369-397 / 6 |
| CLB/NCLC 4 | 4 / 4 / 4 / 4 | 3.5 / 4.0 / 4.5 / 4.0 | 33-41 / 41-50 / 28-38 / 42-50 | 306-351 / 268-329 / 306-351 / 328-386 | 342-374 / 4-5 / 331-368 / 4-5 |

### Work-Experience Primitive

For CRS work factors, the auditor must not blindly import program-eligibility shortcuts. CRS Ministerial Instructions define Canadian work experience and foreign work experience separately. Common predicates:

- Skilled occupation must be in **NOC TEER 0, 1, 2, or 3** unless the specific medical-service unit-group carve-out applies.
- Work must be paid by wages or commission.
- Full-time = **at least 30 hours/week**; part-time equivalent is capped at 30 hours/week; excess/simultaneous full-time work is evaluated as one full-time period.
- NOC claim requires a five-digit NOC code and evidence that the applicant performed the lead statement and a substantial number of main duties, including all essential duties.
- Canadian CRS work: acquired in Canada within the 10 years before points are assigned; full-time study, self-employment for the TEER 0-3 branch, unauthorized work, and work without required temporary-resident status are excluded.
- Foreign CRS work: acquired outside Canada within the 10 years before points are assigned, in one or more TEER 0-3 occupations, paid, full-time/equivalent.
- Program MEC may add separate rules (for example continuous one-year FSW work). Keep CRS-score substantiation separate from MEC validation unless v4.0 explicitly adds an A11.2/MEC sub-check.

## Full CRS Factor Substantiation Map

### A. Core / Human Capital Factors

| CRS factor | Supporting document(s) | Values / thresholds that must match claimed points | Admissibility rules that make proof acceptable | Complexity | Existing dependency / grounding split |
|------------|------------------------|----------------------------------------------------|-----------------------------------------------|------------|---------------------------------------|
| **Age** | Passport/travel-document biographical page; ITA date and round record; birth certificate only if identity/DOB conflict needs backup. | Calculate age on the **date the ITA was issued** for invited applicants. Points: with spouse / without spouse = 17 or less 0/0; 18 = 90/99; 19 = 95/105; 20-29 = 100/110; 30 = 95/105; 31 = 90/99; 32 = 85/94; 33 = 80/88; 34 = 75/83; 35 = 70/77; 36 = 65/72; 37 = 60/66; 38 = 55/61; 39 = 50/55; 40 = 45/50; 41 = 35/39; 42 = 25/28; 43 = 15/17; 44 = 5/6; 45+ = 0/0. | Passport bio page must be clear/legible and match profile identity. If birthday occurs after ITA and before e-APR and lowers score/MEC, do **not** auto-fail; mark `AT-RISK` and cite the A11.2 birthday public-policy consideration. | LOW | Reuse `passport`; corpus-ground point table + A11.2 age exception; structural date math. |
| **Level of education** | Canadian credential proof (degree/diploma/certificate + transcript if available) OR foreign completed credential + ECA report/reference number; translations if non-EN/FR. | Highest education level must map to claimed points. With spouse / without spouse: less than secondary 0/0; secondary 28/30; one-year post-secondary 84/90; two-year post-secondary 91/98; three-year+ post-secondary 112/120; two or more credentials with one 3-year+ 119/128; Master's or eligible entry-to-practice professional degree 126/135; doctoral 140/150. For two-or-more credentials, at least one credential must be for a program of 3+ years. | Foreign education needs ECA for immigration purposes from designated organization/professional body, less than 5 years old at profile/e-APR, indicating equivalency to a **completed** Canadian secondary/post-secondary credential. Canadian credential must meet Canadian educational credential definition/DLI indication. ECA "number of years of study" or non-recognized institution is not enough. | MEDIUM | Reuse `eca`, `proof-of-studies`, `translation`; corpus-ground ECA/education rules; structural highest-level selection. |
| **Official language proficiency — first official language** | Accepted language test result/certificate for selected first official language: CELPIP-G, IELTS General Training, PTE Core, TEF Canada, or TCF Canada. | Extract test type, test date, certificate/form/PIN/reference number, and all four raw scores. Convert each ability to CLB/NCLC using the corpus equivalency chart. Points **per ability** with spouse / without spouse: below CLB 4 = 0/0; CLB 4 or 5 = 6/6; CLB 6 = 8/9; CLB 7 = 16/17; CLB 8 = 22/23; CLB 9 = 29/31; CLB 10+ = 32/34. Max first-language points: 128 with spouse, 136 without. | Test must be an accepted type and correct option; all four abilities present or disability averaging is properly documented; less than 2 years old at required assessment/e-APR; TEF scores must use correct date-specific equivalency column; English uses CLB, French uses NCLC. | HIGH | Reuse `language-test`; corpus-ground accepted tests, conversion, validity, point table; structural per-ability sum/cap. |
| **Official language proficiency — second official language** | Accepted second official language test result/certificate, if claimed. | Convert all four abilities. Points per ability: CLB/NCLC 4 or less = 0; 5-6 = 1; 7-8 = 3; 9+ = 6. Max second-language points: 24 without spouse; **22 with spouse** despite 6-per-ability table. | Same accepted-test, four-ability, validity, TEF date-specific, and disability-averaging rules as first official language. Must be the language not selected as first official language. | HIGH | Reuse `language-test`; corpus-ground second-language cap; structural cap enforcement. |
| **Canadian work experience** | Employer reference/experience letter for each declared Canadian work period; optional/strong supporting docs such as T4 slips and CRA notices of assessment; work permits/status docs if needed to prove authorized work; NOC 2021 corpus for TEER/duties. | Years substantiated in Canada within the 10-year CRS window. With spouse / without spouse: none or <1 year 0/0; 1 year 35/40; 2 years 46/53; 3 years 56/64; 4 years 63/72; 5+ years 70/80. Each period must show dates, hours/week, job title, duties/responsibilities, salary/benefits, employer, and NOC. | Reference letter should be on company letterhead with applicant name, company contact info, supervisor/personnel officer name/title/signature, all positions, dates, hours/week, salary/benefits, duties. Work must be paid, TEER 0-3, acquired in Canada, full-time/equivalent, not unauthorized, not full-time-study period, not excluded self-employment for Canadian CRS work, with temporary resident status. | HIGH | Reuse `employment-reference-letter`; NOC corpus; corpus-ground work rules; structural duration/hours cap and NOC TEER lookup. |

### B. Spouse / Common-Law Partner Factors

Spouse factors apply only when there is an **accompanying spouse/common-law partner who is not a Canadian citizen or permanent resident**. If the spouse is not accompanying, or is a Canadian citizen/permanent resident, the principal applicant is scored as if they do not have a spouse/partner for core factors.

| CRS factor | Supporting document(s) | Values / thresholds that must match claimed points | Admissibility rules that make proof acceptable | Complexity | Existing dependency / grounding split |
|------------|------------------------|----------------------------------------------------|-----------------------------------------------|------------|---------------------------------------|
| **Spouse/common-law partner level of education** | Spouse Canadian credential proof OR spouse foreign completed credential + ECA report/reference number; marriage certificate or common-law proof as relationship context; translations if needed. | Highest spouse education points: less than secondary 0; secondary 2; one-year post-secondary 6; two-year post-secondary 7; three-year+ post-secondary 8; two or more credentials with one 3-year+ 9; Master's/eligible professional degree 10; doctoral 10. | Same ECA/Canadian-credential rules as principal education: designated organization/professional body, immigration-purpose ECA, less than 5 years old, completed-equivalent credential, Canadian DLI indication for Canadian education. | MEDIUM | Reuse `eca`, `proof-of-studies`, `marriage-certificate`, `common-law-union`, `translation`; structural spouse-applicability gate. |
| **Spouse/common-law partner official language proficiency** | Spouse accepted language test result/certificate for spouse's first official language. | Per ability: CLB/NCLC 4 or less = 0; 5-6 = 1; 7-8 = 3; 9+ = 5. Max 20 points. | Accepted test/correct option; all four abilities; less than 2 years old; correct CLB/NCLC conversion; spouse first official language specified. | HIGH | Reuse `language-test`; corpus-ground spouse language grid; structural sum. |
| **Spouse/common-law partner Canadian work experience** | Spouse Canadian employer reference/experience letters for claimed Canadian periods; T4/NOA support if available; work authorization/status docs if needed; NOC 2021 corpus. | Points: none or <1 year 0; 1 year 5; 2 years 7; 3 years 8; 4 years 9; 5+ years 10. | Same Canadian CRS work admissibility as principal: in Canada, within 10 years, TEER 0-3/medical carve-out, paid, 30h/week or equivalent, duties match NOC, unauthorized/full-time-study/excluded self-employment periods not counted. PDI completeness asks proof from spouse/common-law partner if Canadian work experience is claimed. | HIGH | Reuse `employment-reference-letter`; NOC corpus; structural duration/hours cap. |

### C. Skill Transferability Factors

These factors generally require **no new document type**. They recombine substantiated values from education, language, Canadian work, foreign work, and certificate-of-qualification evidence. The hard part is caps: education-combination subtotal max 50; foreign-work-combination subtotal max 50; total skill-transferability max 100.

| CRS factor | Supporting document(s) | Values / thresholds that must match claimed points | Admissibility rules that make proof acceptable | Complexity | Existing dependency / grounding split |
|------------|------------------------|----------------------------------------------------|-----------------------------------------------|------------|---------------------------------------|
| **Education × first official-language proficiency** | Principal education proof/ECA + principal first-official-language test. | Secondary or less = 0. Post-secondary 1+ year + CLB/NCLC 7+ in all first-language abilities with at least one ability <9 = 13; same education + CLB/NCLC 9+ in all abilities = 25. Higher education group (two+ credentials with one 3-year+, Master's/eligible professional, or doctoral) + CLB/NCLC 7+ all with one <9 = 25; + CLB/NCLC 9+ all = 50. | Both component proofs must be independently admissible: valid ECA/Canadian credential and valid accepted language test. Points use **first official language only**. | HIGH | Reuse `eca`, `proof-of-studies`, `language-test`; structural dependency graph and education-subtotal cap. |
| **Education × Canadian work experience** | Principal education proof/ECA + principal Canadian work evidence. | Secondary or less = 0. Post-secondary 1+ year + 1 year Canadian work = 13; +2+ years Canadian work = 25. Higher education group +1 year Canadian work = 25; +2+ years Canadian work = 50. | Component admissibility from education and Canadian-work factors. Canadian work duration must be substantiated after excluding ineligible periods. | HIGH | Reuse `eca`, `proof-of-studies`, `employment-reference-letter`; structural cap with education×language. |
| **Foreign work experience × first official-language proficiency** | Foreign employer reference/experience letters and supporting proof; NOC 2021 corpus; principal first-official-language test. | No foreign work = 0. 1-2 years foreign work + CLB/NCLC 7+ all first-language abilities with at least one <9 = 13; + CLB/NCLC 9+ all = 25. 3+ years foreign work + CLB/NCLC 7+ all with at least one <9 = 25; + CLB/NCLC 9+ all = 50. | Foreign work must be paid, outside Canada, within 10 years, TEER 0-3, full-time/equivalent, with NOC code/duties substantiated. Self-employment may be supported by business ownership, income evidence, and third-party service/payment docs; self-declared duties/affidavits are not acceptable proof. | HIGH | Reuse `employment-reference-letter`, `language-test`, `translation`; NOC corpus; structural duration grouping. |
| **Foreign work experience × Canadian work experience** | Foreign work evidence + Canadian work evidence. | No foreign work = 0. 1-2 years foreign + 1 year Canadian = 13; 1-2 foreign + 2+ Canadian = 25; 3+ foreign + 1 Canadian = 25; 3+ foreign + 2+ Canadian = 50. | Component work proofs must each satisfy their own admissibility rules. Do not double-count hours above full-time; do not conflate FSW continuous-year MEC with CRS foreign-work thresholds unless an MEC check is separately in scope. | HIGH | Reuse `employment-reference-letter`; structural cap with foreign×language. |
| **Certificate of qualification (trades) × first official-language proficiency** | Provincial/territorial/federal certificate of qualification in eligible trade occupation + principal first-official-language test. | 25 points if valid certificate and CLB/NCLC 5+ in all first-language abilities with one or more abilities <7. 50 points if valid certificate and CLB/NCLC 7+ in all abilities. 0 if no valid certificate or below CLB/NCLC 5 in any ability. | Certificate must be valid at ITA and e-APR; issued by a competent Canadian provincial/territorial/federal authority with legally delegated authority; must demonstrate full qualification, not prequalification/apprenticeship/vocational-school credential; occupation must be eligible in the PDI list. Applicant does **not** need work experience in that NOC solely to receive certificate CRS points. | HIGH | Reuse `certificate-of-qualification`, `language-test`; corpus-ground competent-authority and eligible-NOC rules. |

### D. Additional Points

| CRS factor | Supporting document(s) | Values / thresholds that must match claimed points | Admissibility rules that make proof acceptable | Complexity | Existing dependency / grounding split |
|------------|------------------------|----------------------------------------------------|-----------------------------------------------|------------|---------------------------------------|
| **Provincial/territorial nomination** | Nomination certificate / Express Entry nomination acceptance record; profile nomination status; province verification status if available. | 600 points if the applicant is named in an eligible nomination certificate, the nomination has been verified by the province/territory, and the applicant accepted it. 0 if revoked, declined, expired, unverified, or not accepted. | Certificate must be issued by a government under an Express Entry stream covered by current MI/PNP rules; status must not be revoked/declined. Some evidence may be electronic rather than an uploaded document, so the vault needs a "profile system evidence" record type. | MEDIUM | No v3.1 doc agent dedicated to PNP; implement new factor adapter. Corpus-ground MI s.28; structural status check. |
| **Qualifying job offer / arranged employment** | Current CRS substantiation: no document can substantiate current additional CRS points because current corpus says job-offer points were removed as of 2025-03-25 and MI marks the additional factor repealed. For program-eligibility validation only: employer offer letter, LMIA number if any, work permit/employer-specific permit evidence. | **Current rule:** 0 CRS additional points for job offers. Legacy values were 50 for skilled occupation and 200 for NOC Major Group 00, but current/future candidates should not receive them. If the ITA was issued before the 2025-03-25 change or a physician/public-policy edge case appears, mark `AT-RISK` and require MI-in-force-at-ITA research before awarding. | Offer letter, when relevant for eligibility, must be written/recent, not from embassy/high commission/consulate, set out pay/deductions, duties, conditions/hours, and meet program-specific full-time/continuous/LMIA or LMIA-exempt rules. But do not let a valid offer add current CRS points unless corpus proves an applicable legacy rule. | HIGH | Reuse `job-offer`; corpus-ground policy change and any legacy exception; structural effective-date gate. |
| **Post-secondary education in Canada** | Canadian post-secondary credential proof: degree/diploma/certificate/trade or apprenticeship credential; transcripts if available; DLI number; evidence of program length/full-time study/physical presence if not obvious; translations if needed. | 0 for secondary credential. 15 points for eligible Canadian post-secondary credential from a one- or two-year program. 30 points for eligible credential from a program of 3+ years, Master's/eligible professional degree, or doctoral-level program. Only highest eligible credential counts. | Must be obtained for study/training at a Canadian educational institution located in Canada; completed at least 8 months full-time and physically present in Canada for at least 8 months unless COVID-era exception applies (program in whole/part between 2020-03-01 and 2022-08-31). Eligible credential/institution rules exclude ESL/FSL > half, distance learning > half unless exception, and return-home scholarship/fellowship conditions. A11.2 PDI aligns additional education points with eligible/PGWP-like institution/program status; live DLI/PGWP lookup may be needed. | HIGH | Reuse `proof-of-studies`, `translation`; corpus-ground MI/PDI eligibility; structural credential-length classification. |
| **Strong French-language skills** | TEF Canada or TCF Canada French test result; English accepted test result if claiming the larger total. | 25 points if French NCLC 7+ in all four abilities. Additional 25 points (total 50) if English CLB 5+ in all four abilities. If English is CLB 4 or lower or no English test, only 25. | French and English tests must be accepted tests, within 2-year validity, four abilities, and converted by correct CLB/NCLC tables. TEF date-specific conversion is important. | MEDIUM | Reuse `language-test`; corpus-ground additional-points table; structural language-pair evaluation. |
| **Sibling in Canada** | Proof of relationship to sibling of applicant or accompanying spouse/common-law partner; proof of sibling status; proof of current residence in Canada. Examples: birth certificates/adoption documents/official documents showing common parent; Canadian citizenship document, Canadian birth certificate, or PR card (both sides); lease/mortgage/utility bills/residence evidence. | 15 points if applicant or accompanying spouse/common-law partner has at least one sibling who is 18+, Canadian citizen or permanent resident, and living in Canada. Sibling includes biological/adoptive child of the applicant's/spouse's parent, parent's spouse, or parent's common-law partner. | Status document must prove Canadian citizen/PR. Residence evidence should show Canadian address and be recent, dated within 6 months before submission. Relationship proof must establish the sibling link; step-sibling claims should not show the parental marriage/common-law relationship has broken down. | MEDIUM | Reuse `relative-in-canada`, `birth-certificate`, `marriage-certificate`, `common-law-union`, `translation`; corpus-ground proof list and recency. |

## Extraction Schema: Minimum Fields by Evidence Type

| Evidence type | Required extracted fields | Used by factors |
|---------------|--------------------------|-----------------|
| CRS/ITA profile snapshot | ITA date, round number, lowest invited score, claimed total CRS, claimed factor breakdown, spouse/accompanying status, first/second official language selection, claimed NOC codes, claimed education/work durations. | All factors; score-impact report. |
| Passport / identity | Name, date of birth, document number, expiry, nationality, profile-name match. | Age; identity cross-checks; spouse/family context. |
| Language test | Test type/option, test date, certificate/form/PIN/reference, language, four raw scores, any disability averaged scores, issuer. | Core language; spouse language; skill transferability; French additional points. |
| ECA report | Issuer, issue date, report/reference number, immigration-purpose marker, credential(s), Canadian equivalency outcome, completed credential marker, professional-body applicability. | Core/spouse education; skill transferability education. |
| Canadian education proof | Institution, DLI number, program/credential, credential issue date, program length, full-time months, in-Canada location/physical presence, distance-learning/ESL/scholarship flags. | Core education; Canadian-study additional; skill transferability education. |
| Employment reference | Employer, country, job title, NOC code claimed, dates, current job status, hours/week, salary/benefits, duties/responsibilities, signatory/contact/letterhead, self-employment evidence if applicable. | Canadian/foreign work; spouse Canadian work; skill transferability. |
| Work authorization / tax support | Work permit employer, validity, status, LMIA basis/exemption if relevant, T4/NOA years. | Canadian work; job-offer eligibility edge cases. |
| Certificate of qualification | Issuing authority, jurisdiction, trade/NOC, certificate type, issue/expiry/validity, Red Seal/authority markers, prequalification/apprenticeship flags. | Skill transferability certificate. |
| Job offer | Employer(s), start date, duration, full-time hours, paid/non-seasonal, duties, NOC/TEER, LMIA number or LMIA-exempt basis, work permit employer, embassy/ineligible-employer flags. | Arranged employment policy row; FSW/FST eligibility if later in scope. |
| PNP nomination | Issuing province/territory, certificate number, stream, named applicant, accepted/verified status, expiry/revocation status. | Provincial nomination. |
| Relative/sibling evidence | Relative name/DOB, status proof, current Canadian address/date, relationship chain documents, common-parent evidence, step-sibling relationship status. | Sibling in Canada. |

## Feature Dependencies

```text
Existing authoritative corpus + FTS5 search + citation resolver
    └──grounds──> CRS rule registry (factor ids, predicates, citations)
                       └──feeds──> Four auditor modules

Candidate vault (git-ignored)
    ├──stores──> ITA/profile factor breakdown + round cutoff
    ├──stores──> raw documents
    ├──stores──> extracted values + extraction confidence
    └──stores──> user confirmations

Document extraction
    └──requires──> confirm-what-I-read checkpoint
                       └──enables──> presence/value/admissibility checks

Existing v3.1 document agents
    ├──language-test ──feeds──> core/spouse/transfer/French language factors
    ├──eca + proof-of-studies ──feeds──> education + Canadian-study factors
    ├──employment-reference-letter ──feeds──> Canadian/foreign work factors
    ├──certificate-of-qualification ──feeds──> trade certificate factor
    ├──job-offer ──feeds──> arranged-employment policy/eligibility row
    ├──passport ──feeds──> age identity
    └──relative/birth/marriage/common-law/translation ──feeds──> spouse + sibling factors

Factor verdicts
    └──aggregate──> substantiated CRS total
                       └──compare──> ITA round cutoff
```

### Dependency Notes

- **Rule registry before agents:** Auditor modules should not each invent CRS rules. Encode once, cite once, reuse everywhere.
- **Extraction before substantiation:** Presence-only checks are insufficient; the auditor needs parsed values. But extraction confirmation must precede green verdicts.
- **Core factors feed transferability:** Education, language, and work evidence fan out into multiple skill-transferability combinations. The UI should show this fan-out.
- **NOC corpus is a first-class dependency:** Work factors require TEER and duties, not just titles.
- **Translation remains cross-cutting:** Any non-English/French proof package must satisfy the translation rules already covered by v3.1.
- **Job offer is a policy trap:** Keep "valid job offer for eligibility" separate from "CRS arranged-employment additional points." Current additional points are removed.
- **Round/MI snapshot matters:** A11.2 says applications are assessed under the Ministerial Instructions in force during the round of invitation; store the ITA round and MI/corpus version used.

## MVP Definition

### Launch With (v4.0)

- [ ] **Candidate vault** for CRS profile, ITA round/cutoff, raw docs, extracted fields, confirmations, verdicts, and citations — essential privacy foundation.
- [ ] **Extraction pipeline with confirmation** for the evidence types in the schema above — essential because value matching is the new capability.
- [ ] **Grounded CRS rule registry** covering every factor id and threshold in this file — essential to keep the existing fail-closed trust model.
- [ ] **Four auditor modules**: core, spouse, skill transferability, additional points — essential for context-light full-grid coverage.
- [ ] **Factor-card report** with `SUBSTANTIATED` / `GAP` / `AT-RISK` / `N/A`, evidence pointer, cited predicate, extracted value, claimed value, substantiated points, and score delta.
- [ ] **Arranged-employment current-policy guard** — essential because stale job-offer points are high-risk and recently changed.

### Add After Validation (v4.0.x)

- [ ] **Legacy/edge-case arranged-employment research path** — for pre-2025-03-25 ITAs and physician public-policy wording conflicts.
- [ ] **Live DLI/PGWP eligibility verifier** — Canadian-study additional points may need live DLI/program lookup beyond the static corpus snapshot.
- [ ] **Work-duty confidence scoring** — deterministic markers first; deeper semantic matching remains constrained by no-cloud/no-vector decisions.
- [ ] **MEC sidecar checks** — FSW/FST/CEC minimum-entry criteria are A11.2-relevant but not identical to CRS-factor substantiation.
- [ ] **Document-specific fix checklist** — "get a new language test", "request amended reference letter with hours/salary/duties", "add sibling residence proof dated within 6 months."

### Future Consideration (v5+)

- [ ] Pre-ITA CRS planning/optimization — deliberately separate product.
- [ ] Multi-applicant/family dashboard beyond CRS-relevant proof.
- [ ] Lawyer/RCIC review export packet — useful but must avoid representing legal advice as system judgment.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Candidate vault + privacy guard | HIGH | HIGH | P1 |
| CRS rule registry | HIGH | HIGH | P1 |
| Extraction + confirmation | HIGH | HIGH | P1 |
| Core human-capital auditor | HIGH | MEDIUM | P1 |
| Skill-transferability auditor | HIGH | HIGH | P1 |
| Additional-points auditor | HIGH | HIGH | P1 |
| Spouse/common-law auditor | HIGH when applicable | MEDIUM | P1 |
| Score-impact/cutoff report | HIGH | MEDIUM | P1 |
| Arranged-employment policy guard | HIGH | MEDIUM | P1 |
| Live DLI/PGWP lookup | MEDIUM | MEDIUM | P2 |
| MEC sidecar checks | MEDIUM | HIGH | P2 |
| Enhanced duty semantic matching | MEDIUM | HIGH | P3 |

**Priority key:** P1 = must have for v4.0 launch · P2 = add after core auditor works · P3 = future / research-heavy.

## Phase-Splitting Recommendation for Roadmap

1. **Vault + CRS claim schema** — unblock all later modules; codify factor ids and evidence references.
2. **Extraction + confirmation** — create the value layer the auditor needs; keep non-grounded extraction separate from grounded rules.
3. **Grounded rule registry** — encode CRS grids, language conversion, ECA/work/certificate/job-offer/Canadian-study/sibling predicates with citations.
4. **Core + spouse modules** — simpler factor groups; validate the verdict contract and UI.
5. **Skill transferability module** — depends on core extracted values and cap logic.
6. **Additional-points module** — includes high-risk policy and evidence diversity (PNP, job offer, Canadian study, French, sibling).
7. **Aggregate score/cutoff report** — compare substantiated total to ITA cutoff after all factor modules emit points.

## Research Flags for Requirements Authors

- **Arranged employment:** Current rule removes CRS job-offer points, but the job-offer page also contains physician public-policy wording and MI has a legacy transition clause. Treat any non-zero job-offer CRS claim as `AT-RISK` until the ITA-era MI and applicable public policy are resolved from corpus.
- **Canadian study additional points:** Need exact DLI/PGWP/program eligibility data at e-APR time. Static corpus rules are clear, but institution/program status may require refreshed lookup.
- **Foreign work continuity:** CRS MI says foreign work for sections 23/24 can be in one or more TEER 0-3 occupations; some calculator/program language mentions "one occupation" or continuous-year MEC. Do not mix CRS substantiation with program MEC without explicit citations.
- **Work-duty matching:** NOC duties are not purely numeric. Start with reference-letter required fields and deterministic NOC markers; label ambiguous cases `AT-RISK`.
- **Extraction failures:** A low-confidence OCR parse must never become a green factor. Confirmation is an acceptance criterion, not a nice-to-have.

## Sources

All authoritative sources below are already present in the local corpus and should be cited by chunk id at implementation time:

- `corpus/ministerial-instructions/current.md` — CRS factor categories, point grids, work definitions, skill-transferability caps, PNP, Canadian study, sibling, French, job-offer repeal/current MI.
- `corpus/pr-pdi/express-entry-assessing-electronic-application-on-section-a11-2.md` — e-APR/A11.2 substantiation model, CRS score maintenance, refusal consequences, education/certificate assessment guidance, birthday exception, settlement-funds non-CRS note.
- `corpus/pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md` — e-APR completeness, supporting documentation, work reference letter requirements, proof of studies, certificate of qualification, job offer letter, relative/sibling proof, translation.
- `corpus/guidance/language-test.md`, `corpus/language/test-equivalency-charts.md`, `corpus/language/designated-testing-agencies.md` — accepted language tests, validity, program thresholds, CLB/NCLC conversion tables, test-option restrictions.
- `corpus/guidance/education-assessment.md`, `corpus/eca/educational-credential-assessment.md` — ECA validity, designated organizations/professional bodies, completed credential equivalency, ECA outcome conversion.
- `corpus/guidance/job-offer.md` — current job-offer points removal, valid job-offer criteria for eligibility, LMIA/LMIA-exempt logic.
- `corpus/guidance/crs-criteria.md` and `corpus/guidance/criteria-comprehensive-ranking-system.md` — user-facing CRS criteria, spouse scoring mode, calculator prompts including age-at-ITA and document inputs.
- `corpus/guidance/documents.md` and `corpus/guidance/apply-permanent-residence.md` — document preparation, upload, translation, passport, and e-APR process guidance.
- `corpus/noc-2021/*.md` — StatCan NOC 2021 TEER, lead statements, and main duties for work-factor substantiation.

---
*Feature research for: v4.0 CRS Profile ↔ Document Substantiation Auditor*  
*Researched: 2026-07-05*
