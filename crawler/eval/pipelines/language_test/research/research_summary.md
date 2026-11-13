# Research Summary: language_test

## Executive Summary

Online research into IRCC operational guidance and Express Entry requirements reveals major failure modes for language test documents: language test validity expiration exceeding the strict 2-year limit, Test Report Form (TRF) or registration number mismatches triggering verification failures or Procedural Fairness Letters (PFLs) under misrepresentation concerns, language component scores falling below minimum Canadian Language Benchmark (CLB) cutoffs for specific economic streams, and submission of unapproved test formats such as IELTS Academic or IELTS One Skill Retake.

## Identified Failure Modes

| ID | Category | Severity | Title | Authority Classification | Citation | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| PFL-LANGUAGE-01 | pfl_incomplete_evidence | critical | Language Test Results Expired (> 2 Years Old at e-APR) | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/language-test.html | The applicant must take a new IRCC-approved language test and obtain valid results before submitting the e-APR. If the current invitation to apply (ITA) window is too short, the applicant should decline the ITA and re-enter the pool with valid language test results. |
| PFL-LANGUAGE-02 | pfl_misrepresentation | critical | Test Report Form (TRF) Number Mismatch or Unverifiable Test Results | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/language-test.html | The applicant must respond to the PFL within the specified deadline, providing a high-resolution copy of the official Test Report Form, explaining any typographical discrepancy in the TRF/PIN entry, and authorizing direct provider verification if necessary. |
| PFL-LANGUAGE-03 | pfl_incomplete_evidence | critical | Individual Component Scores Below Minimum Program CLB Cutoff | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/language-test.html | The applicant must re-sit an approved language examination to achieve scores meeting or exceeding the minimum required CLB thresholds for all four language abilities before applying. |
| PFL-LANGUAGE-04 | pfl_incomplete_evidence | critical | Submission of Unapproved Test Stream or Unaccepted Retake Variant | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/language-test.html | The applicant must take a fully approved language test designation (e.g., IELTS General Training, CELPIP-General, PTE Core, TEF Canada, or TCF Canada) and submit valid results from a full single test session. |

## Failure Mode Details

### PFL-LANGUAGE-01: Language Test Results Expired (> 2 Years Old at e-APR)
- **Authority Classification:** discovery
- **Description:** IRCC requires language test results to be valid (less than 2 years old) both when entering the Express Entry pool and on the date the electronic Application for Permanent Residence (e-APR) is submitted. If test results expire prior to e-APR submission, the application is rejected as incomplete under Section R10 of the IRPR or refused for failing minimum entry criteria.
- **Affected Fields:** test_date, expiry_date, validity_status
- **Remediation Hypothesis:** The applicant must take a new IRCC-approved language test and obtain valid results before submitting the e-APR. If the current invitation to apply (ITA) window is too short, the applicant should decline the ITA and re-enter the pool with valid language test results.
- **Supporting Excerpt (Online):** Your test results must be less than 2 years old when you: complete your Express Entry profile, and submit your application for permanent residence... If you apply for permanent residence with language test results that have expired, we'll refuse your application.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-LANGUAGE-02: Test Report Form (TRF) Number Mismatch or Unverifiable Test Results
- **Authority Classification:** discovery
- **Description:** Entering an inaccurate TRF number, PIN, or Registration Number in the profile/e-APR, or providing document details that cannot be verified against official language testing organization databases (e.g., IELTS, CELPIP, PTE online portals), causes an integrity flag and triggers a Procedural Fairness Letter (PFL) for suspected misrepresentation under A40.
- **Affected Fields:** trf_number, test_pin, registration_number, candidate_id
- **Remediation Hypothesis:** The applicant must respond to the PFL within the specified deadline, providing a high-resolution copy of the official Test Report Form, explaining any typographical discrepancy in the TRF/PIN entry, and authorizing direct provider verification if necessary.
- **Supporting Excerpt (Online):** enter the test results into your Express Entry profile (and the language test result form or certificate number and test PIN, if the system asks for it)... We'll verify both the averaged scores and the language test results you submit.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-LANGUAGE-03: Individual Component Scores Below Minimum Program CLB Cutoff
- **Authority Classification:** discovery
- **Description:** Submitting language test results where any individual component skill score (speaking, listening, reading, writing) falls below the mandatory minimum CLB cutoff for the selected program (e.g., CLB 7 across all 4 abilities for FSWP; CLB 7 for CEC TEER 0/1; CLB 5/4 for FSTP) leads to immediate refusal for failure to meet program eligibility requirements.
- **Affected Fields:** speaking_score, listening_score, reading_score, writing_score, clb_level
- **Remediation Hypothesis:** The applicant must re-sit an approved language examination to achieve scores meeting or exceeding the minimum required CLB thresholds for all four language abilities before applying.
- **Supporting Excerpt (Online):** Federal Skilled Worker Program First official language Minimum level for all 4 abilities CLB 7... Canadian Experience Class Minimum level for all 4 abilities NOC TEER 0/1 CLB 7.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-LANGUAGE-04: Submission of Unapproved Test Stream or Unaccepted Retake Variant
- **Authority Classification:** discovery
- **Description:** Submitting an unapproved language test version (such as IELTS Academic instead of IELTS General Training, TOEFL, or using IELTS One Skill Retake, which IRCC does not accept for Express Entry) renders the proof invalid, resulting in rejection at the Section R10 completeness check stage.
- **Affected Fields:** test_type, test_provider, test_variant
- **Remediation Hypothesis:** The applicant must take a fully approved language test designation (e.g., IELTS General Training, CELPIP-General, PTE Core, TEF Canada, or TCF Canada) and submit valid results from a full single test session.
- **Supporting Excerpt (Online):** You must prove your language skills by taking an approved language test... You can take any of these approved language tests: CELPIP-General, IELTS General Training, PTE Core, TEF Canada, TCF Canada.
- **Local Corpus Evidence:** Not verified in local corpus
