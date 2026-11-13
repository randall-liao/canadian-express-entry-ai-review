# Research Summary: educational_credential_assessment

## Executive Summary

Online research on IRCC Express Entry requirements for Educational Credential Assessments (ECA) reveals key failure modes leading to section R10 completeness rejections, section 11.2 eligibility refusals, or Procedural Fairness Letters (PFL). Major triggers include expired ECA reports older than 5 years, foreign credentials from non-accredited or non-recognized institutions, assessments conducted by non-designated bodies or issued for general employment rather than IRCC immigration purposes, and name/reference number discrepancies that prevent electronic verification.

## Identified Failure Modes

| ID | Category | Severity | Title | Authority Classification | Citation | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| PFL-EDUCATIO-01 | pfl_validity_expired | critical | ECA Report Expired Beyond 5-Year Validity Period | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/education-assessment.html | Obtain a re-issued or updated ECA report from the original designated assessing agency (e.g., WES, ICAS, CES) prior to submitting the eAPR, ensuring the issue date on the new report is within the 5-year window. |
| PFL-EDUCATIO-02 | pfl_credential_unrecognized | critical | Foreign Credential From Non-Accredited Institution or Lacks Canadian Equivalency | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/education-assessment.html | The applicant must claim CRS education points only for completed credentials that hold explicit Canadian equivalency. If a secondary higher education credential is unaccredited, submit an alternative ECA for another eligible, recognized qualification or higher completed degree. |
| PFL-EDUCATIO-03 | pfl_invalid_issuing_body | critical | ECA Report Issued by Non-Designated Organization or Wrong Assessment Type | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/education-assessment.html | Request an upgrade or re-issuance from a designated assessment agency explicitly specifying IRCC/immigration purposes, or re-apply through an authorized body (e.g., Medical Council of Canada for physicians) before eAPR submission. |
| PFL-EDUCATIO-04 | pfl_identity_mismatch | high | Applicant Name Mismatch or Incorrect Reference Number Preventing Verification | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/education-assessment.html | Ensure the ECA reference number is transcribed exactly. If the ECA reflects a maiden or previous legal name, provide official supporting evidence (e.g., marriage certificate, legal name change certificate, sworn affidavit) along with a cover letter explaining the name variation. |

## Failure Mode Details

### PFL-EDUCATIO-01: ECA Report Expired Beyond 5-Year Validity Period
- **Authority Classification:** discovery
- **Description:** IRCC requires that an Educational Credential Assessment (ECA) report be less than 5 years old on both the date the Express Entry profile is submitted and the date the permanent residence application (eAPR) is submitted. Submitting an application with an ECA report older than 5 years results in immediate rejection under Section R10 or refusal under Section 11.2 for loss of CRS points.
- **Affected Fields:** eca_issue_date, eca_reference_number, crs_education_points
- **Remediation Hypothesis:** Obtain a re-issued or updated ECA report from the original designated assessing agency (e.g., WES, ICAS, CES) prior to submitting the eAPR, ensuring the issue date on the new report is within the 5-year window.
- **Supporting Excerpt (Online):** Your ECA report must be less than 5 years old on the date you submit your profile and your application for permanent residence. If your ECA expires before you apply, IRCC will refuse your application.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-EDUCATIO-02: Foreign Credential From Non-Accredited Institution or Lacks Canadian Equivalency
- **Authority Classification:** discovery
- **Description:** If the designated assessing body determines that the applicant's foreign degree, diploma, or certificate was awarded by an unaccredited institution or does not equal at least a completed Canadian secondary or post-secondary educational credential, IRCC will disallow CRS points for education, leading to profile ineligible determination or application refusal.
- **Affected Fields:** foreign_institution_name, credential_level, canadian_equivalency_summary
- **Remediation Hypothesis:** The applicant must claim CRS education points only for completed credentials that hold explicit Canadian equivalency. If a secondary higher education credential is unaccredited, submit an alternative ECA for another eligible, recognized qualification or higher completed degree.
- **Supporting Excerpt (Online):** To receive points, your ECA report must show that your completed foreign credential is equal to a completed Canadian secondary school (high school) or post-secondary credential. If your assessment says your credential isn't equivalent to a Canadian credential, you won't get any points.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-EDUCATIO-03: ECA Report Issued by Non-Designated Organization or Wrong Assessment Type
- **Authority Classification:** discovery
- **Description:** IRCC accepts ECAs only from specific designated organizations (such as WES, ICAS, CES, IQAS, ICES, or medical/pharmacy professional boards). Submitting an evaluation from an unapproved agency, or submitting a general evaluation intended for employment/academic admission rather than IRCC immigration purposes, fails the R10 completeness check.
- **Affected Fields:** issuing_organization, eca_report_type, eca_reference_number
- **Remediation Hypothesis:** Request an upgrade or re-issuance from a designated assessment agency explicitly specifying IRCC/immigration purposes, or re-apply through an authorized body (e.g., Medical Council of Canada for physicians) before eAPR submission.
- **Supporting Excerpt (Online):** You must get your ECA from an organization or professional body designated by IRCC. Assessments by non-designated organizations will not be accepted. You must make sure you order an ECA report specifically for immigration purposes.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-EDUCATIO-04: Applicant Name Mismatch or Incorrect Reference Number Preventing Verification
- **Authority Classification:** discovery
- **Description:** Discrepancies between the applicant's name on their passport/Express Entry profile and the name on the ECA report (e.g., maiden name vs. married name, missing middle names), or entering an incorrect ECA reference number, prevents automated electronic validation with the evaluation agency and triggers a Procedural Fairness Letter (PFL) or application rejection.
- **Affected Fields:** applicant_given_names, applicant_family_name, eca_reference_number
- **Remediation Hypothesis:** Ensure the ECA reference number is transcribed exactly. If the ECA reflects a maiden or previous legal name, provide official supporting evidence (e.g., marriage certificate, legal name change certificate, sworn affidavit) along with a cover letter explaining the name variation.
- **Supporting Excerpt (Online):** The name on your ECA report must match the name on your Express Entry profile and application. You must enter the exact ECA reference number into your profile so IRCC can verify the assessment online directly with the issuing agency.
- **Local Corpus Evidence:** Not verified in local corpus
