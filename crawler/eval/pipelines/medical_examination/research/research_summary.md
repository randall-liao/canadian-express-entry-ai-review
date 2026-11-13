# Research Summary: medical_examination

## Executive Summary

Live research into IRCC operational instructions and permanent residence application guidelines reveals key failure modes for Express Entry medical examinations: submission of expired medical exam results (>12 months), examinations conducted by non-designated doctors/panel physicians, unresolved medical furtherance requests/incomplete follow-up testing, and missing upfront eMedical receipts during initial completeness checks.

## Identified Failure Modes

| ID | Category | Severity | Title | Authority Classification | Citation | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| PFL-MEDICAL_-01 | pfl_expired_document | critical | Expired Immigration Medical Examination Results Exceeding 12-Month Validity Period | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/medical-police/medical-exams/requirements-permanent-residents.html | The applicant should await formal instruction before completing a new exam unless qualifying for an in-Canada 5-year IME public policy exemption (and providing their prior IME number). If requested via PFL/IMM 1017, complete a new IME with an authorized panel physician within 30 days and submit updated eMedical proof via IRCC Web Form. |
| PFL-MEDICAL_-02 | pfl_invalid_issuer | critical | Medical Examination Administered by Non-Designated / Unassigned Panel Physician | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/medical-police/medical-exams/required/medical-exam-doctor.html | Schedule an immediate examination with an officially authorized IRCC Panel Physician from the official directory. Complete the full IME and submit the resulting IMM 1017B Upfront Medical Report form or eMedical Information Printout Sheet along with a Letter of Explanation in response to the PFL. |
| PFL-MEDICAL_-03 | pfl_incomplete_evidence | high | Incomplete Medical Condition Follow-up and Unresolved Furtherance Requirements | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/inadmissibility/reasons/medical-inadmissibility.html | Attend required specialist appointments without delay, obtain complete diagnostic reports addressing the specific health concerns raised by IRCC, and submit all documentation within the PFL deadline (or request an official extension with appointment booking confirmations if clinic delays occur). |
| PFL-MEDICAL_-04 | pfl_missing_required_document | critical | Missing Upfront Medical Examination Proof at Completeness Check | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/common-supporting-documents.html | Ensure that the document uploaded is the official IMM 1017B Upfront Medical Report Form or eMedical Information Sheet provided by the panel physician showing the applicant's photo, IME/UMI number, and panel physician credentials, rather than a generic billing/appointment receipt. |

## Failure Mode Details

### PFL-MEDICAL_-01: Expired Immigration Medical Examination Results Exceeding 12-Month Validity Period
- **Authority Classification:** discovery
- **Description:** Immigration medical examination (IME) results are valid for exactly 12 months from the date of assessment. When application processing extends beyond 12 months, or when an applicant submits an eMedical receipt from an exam taken over a year prior, IRCC flags the assessment as expired. IRCC will issue a Procedural Fairness Letter or Re-medical Instruction Form (IMM 1017) requiring a updated IME or valid exemption proof.
- **Affected Fields:** ime_number, examination_date, emedical_receipt
- **Remediation Hypothesis:** The applicant should await formal instruction before completing a new exam unless qualifying for an in-Canada 5-year IME public policy exemption (and providing their prior IME number). If requested via PFL/IMM 1017, complete a new IME with an authorized panel physician within 30 days and submit updated eMedical proof via IRCC Web Form.
- **Supporting Excerpt (Online):** Immigration medical exam (IME) results are valid for 12 months from the date of the examination. If your medical exam has expired, you may be required to undergo a new one if a decision has not been made on your application within that period.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-MEDICAL_-02: Medical Examination Administered by Non-Designated / Unassigned Panel Physician
- **Authority Classification:** discovery
- **Description:** IRCC regulations require all immigration medical examinations to be conducted strictly by an IRCC-approved Panel Physician listed in the official physician registry. Submitting medical certificates or evaluation reports issued by a personal primary physician or non-panel clinic results in rejection at completeness check or issuance of a PFL due to lack of medical assessment authority.
- **Affected Fields:** panel_physician_id, clinic_name, physician_signature, emedical_receipt
- **Remediation Hypothesis:** Schedule an immediate examination with an officially authorized IRCC Panel Physician from the official directory. Complete the full IME and submit the resulting IMM 1017B Upfront Medical Report form or eMedical Information Printout Sheet along with a Letter of Explanation in response to the PFL.
- **Supporting Excerpt (Online):** You must see a doctor on the list of panel physicians. Your own doctor can’t do the medical exam. The panel physician doesn’t make the final decision about your medical exam. We make that decision.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-MEDICAL_-03: Incomplete Medical Condition Follow-up and Unresolved Furtherance Requirements
- **Authority Classification:** discovery
- **Description:** When initial medical screening uncovers health concerns or abnormal findings (e.g., chest X-ray findings or chronic illnesses), the IRCC Medical Officer requests additional tests or specialist reports (furtherance). Failing to complete requested follow-up evaluations or failing to submit specialist reports within the specified timeframe triggers a Procedural Fairness Letter for potential medical inadmissibility or non-compliance.
- **Affected Fields:** furtherance_status, specialist_report, laboratory_results, medical_history_questionnaire
- **Remediation Hypothesis:** Attend required specialist appointments without delay, obtain complete diagnostic reports addressing the specific health concerns raised by IRCC, and submit all documentation within the PFL deadline (or request an official extension with appointment booking confirmations if clinic delays occur).
- **Supporting Excerpt (Online):** If we believe you may be medically inadmissible, we’ll send you a letter which explains the reason why. This letter is called a procedural fairness letter. You’ll receive this letter before a final decision is made on your application. You’ll have the opportunity to submit information to respond.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-MEDICAL_-04: Missing Upfront Medical Examination Proof at Completeness Check
- **Authority Classification:** discovery
- **Description:** Express Entry applications require proof of an upfront immigration medical examination (IMM 1017B form or eMedical Information Sheet) uploaded at initial submission. Uploading an administrative payment receipt only, an unreadable document, or omitting proof entirely causes application rejection and return as incomplete during completeness screening.
- **Affected Fields:** emedical_receipt, imm1017b_form, document_attachment
- **Remediation Hypothesis:** Ensure that the document uploaded is the official IMM 1017B Upfront Medical Report Form or eMedical Information Sheet provided by the panel physician showing the applicant's photo, IME/UMI number, and panel physician credentials, rather than a generic billing/appointment receipt.
- **Supporting Excerpt (Online):** If you complete an upfront medical examination before submitting your Express Entry application, you should include the proof of your medical exam (such as the document or receipt given to you by the panel physician) with your application.
- **Local Corpus Evidence:** Not verified in local corpus
