# Research Summary: written_job_offer_lmia

## Executive Summary

Live research on official IRCC operational instructions and ESDC guidelines for Express Entry document type 'written_job_offer_lmia' identified four primary failure modes and PFL triggers under IRPR s. 82(1): submission with an expired LMIA or loss of valid work authorization, offer duration failing the 1-year continuous full-time post-PR requirement, NOC TEER code and duty misalignment, and offering wages below ESDC regional prevailing median rates.

## Identified Failure Modes

| ID | Category | Severity | Title | Authority Classification | Citation | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| PFL-WRITTEN-LMIA-01 | pfl_expired_lmia_validity | critical | LMIA Expired Prior to Application Submission or Loss of Work Authorization | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/job-offer.html | Provide a newly issued positive LMIA decision letter from ESDC naming the applicant and position, or submit proof that the candidate remains authorized and actively employed with the specified employer under an unexpired LMIA-based work permit. |
| PFL-WRITTEN-LMIA-02 | pfl_non_permanent_duration | critical | Job Offer Duration Less Than 1 Year Post-PR Issuance, Part-Time, or Seasonal | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/job-offer.html | Obtain an updated and signed job offer letter from the employer explicitly stating that the position is for full-time work (at least 30 hours per week), continuous, non-seasonal, and for an indeterminate period or at least 1 year after PR visa issuance. |
| PFL-WRITTEN-LMIA-03 | pfl_noc_teer_mismatch | critical | NOC TEER Ineligibility or Duty Discrepancy Between Job Offer Letter and LMIA | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/job-offer.html | Submit an official supplemental job description letter signed by the employer clarifying the position's core duties and demonstrating full alignment with the approved NOC TEER 0, 1, 2, or 3 occupation specified on the LMIA. |
| PFL-WRITTEN-LMIA-04 | pfl_wage_below_prevailing_rate | high | Offered Wage Rate Below Regional ESDC Prevailing Wage or Approved LMIA Rate | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/hire-temporary-foreign/find-need-labour-market-impact-assessment.html | Provide a wage adjustment letter from the employer confirming an updated pay rate that meets or exceeds the current ESDC regional median prevailing wage for the designated NOC, supported by recent pay stubs if the applicant is actively working. |

## Failure Mode Details

### PFL-WRITTEN-LMIA-01: LMIA Expired Prior to Application Submission or Loss of Work Authorization
- **Authority Classification:** discovery
- **Description:** The Labour Market Impact Assessment (LMIA) supporting the written job offer expired before the applicant submitted the electronic Application for Permanent Residence (e-APR), or the applicant ceased working under valid work permit authorization for the designated employer prior to PR visa issuance.
- **Affected Fields:** lmia_number, lmia_expiry_date, job_offer_date, work_permit_status
- **Remediation Hypothesis:** Provide a newly issued positive LMIA decision letter from ESDC naming the applicant and position, or submit proof that the candidate remains authorized and actively employed with the specified employer under an unexpired LMIA-based work permit.
- **Supporting Excerpt (Online):** It must also be made: by an employer with a new positive LMIA that approves the offer and names you and your position... you're authorized to work in Canada on the day you apply for a permanent resident visa, and when the visa is issued
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-WRITTEN-LMIA-02: Job Offer Duration Less Than 1 Year Post-PR Issuance, Part-Time, or Seasonal
- **Authority Classification:** discovery
- **Description:** The written job offer letter states a fixed-term contract expiring in less than 1 year following permanent resident status grant, indicates part-time employment (<30 hours per week), or classifies the job as seasonal, violating IRPR section 82(1) eligibility criteria.
- **Affected Fields:** employment_type, hours_per_week, job_duration, job_end_date
- **Remediation Hypothesis:** Obtain an updated and signed job offer letter from the employer explicitly stating that the position is for full-time work (at least 30 hours per week), continuous, non-seasonal, and for an indeterminate period or at least 1 year after PR visa issuance.
- **Supporting Excerpt (Online):** A valid job offer has to be: from 1 employer, continuous, paid, full-time (at least 30 hours a week), not seasonal, for at least 1 year if you're accepted as a permanent resident
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-WRITTEN-LMIA-03: NOC TEER Ineligibility or Duty Discrepancy Between Job Offer Letter and LMIA
- **Authority Classification:** discovery
- **Description:** The duties and responsibilities detailed in the written job offer letter do not match the lead duties of the approved LMIA or represent a non-qualifying NOC TEER category (TEER 4 or 5 instead of TEER 0, 1, 2, or 3), triggering a Procedural Fairness Letter due to job offer invalidity.
- **Affected Fields:** noc_code, teer_category, job_title, duties_and_responsibilities
- **Remediation Hypothesis:** Submit an official supplemental job description letter signed by the employer clarifying the position's core duties and demonstrating full alignment with the approved NOC TEER 0, 1, 2, or 3 occupation specified on the LMIA.
- **Supporting Excerpt (Online):** in a NOC TEER category 0, 1, 2 or 3... set out details of the job they're offering you, such as: your pay and deductions, your duties, the conditions of employment
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-WRITTEN-LMIA-04: Offered Wage Rate Below Regional ESDC Prevailing Wage or Approved LMIA Rate
- **Authority Classification:** discovery
- **Description:** The wage rate listed in the written offer letter is below the median prevailing wage for the NOC and geographic location published by ESDC/Job Bank, or is lower than the wage approved in the positive LMIA decision letter, violating LMIA conditions.
- **Affected Fields:** wage_rate, pay_frequency, lmia_wage_offered, prevailing_wage_rate
- **Remediation Hypothesis:** Provide a wage adjustment letter from the employer confirming an updated pay rate that meets or exceeds the current ESDC regional median prevailing wage for the designated NOC, supported by recent pay stubs if the applicant is actively working.
- **Supporting Excerpt (Online):** The employer must pay at least the prevailing wage for the occupation in the location where the work will be performed.
- **Local Corpus Evidence:** Not verified in local corpus
