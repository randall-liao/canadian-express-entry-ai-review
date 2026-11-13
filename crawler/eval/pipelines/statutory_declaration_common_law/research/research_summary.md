# Research Summary: statutory_declaration_common_law

## Executive Summary

Online research findings reveal that failure modes for Express Entry 'statutory_declaration_common_law' (IMM 5409) center on lack of proper notarization/solemnization, cohabitation periods falling short of 12 continuous months or containing unexplained gaps, insufficient documentary evidence proving joint financial interdependence, and cross-form address/date discrepancies between IMM 5409, Express Entry personal history, and CRA/identity records.

## Identified Failure Modes

| ID | Category | Severity | Title | Authority Classification | Citation | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| PFL-STATUTOR-01 | pfl_invalid_legal_declaration | critical | IMM 5409 Statutory Declaration Missing Notarization, Official Stamp, or Valid Solemnization Signature | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/statutory-declaration-common-law-union.html | Re-execute IMM 5409 in the presence of an authorized Notary Public or Commissioner for Oaths who must affix their official seal, commission expiration date, and signature. Submit a letter of explanation and sworn affidavit confirming proper execution. |
| PFL-STATUTOR-02 | pfl_cohabitation_duration_gap | critical | Failure to Demonstrate 12 Consecutive Months of Continuous Cohabitation Prior to Application Submission | discovery | https://ircc.canada.ca/english/helpcentre/answer.asp?qnum=346&top=14 | Submit a continuous month-by-month residential chronology covering the full 12-month period, including employer travel letters or travel itineraries to explain short temporary absences, along with additional concurrent evidence (e.g. government correspondence, rental receipts, joint utilities) proving unbroken shared living. |
| PFL-STATUTOR-03 | pfl_insufficient_financial_interdependence | high | Lack of Joint Financial Arrangements or Shared Financial Interdependence Evidence | discovery | https://ircc.canada.ca/english/helpcentre/answer.asp?qnum=347&top=14 | Provide comprehensive documentary proof of financial integration over the full 12-month cohabitation period, such as joint bank statements showing regular shared household expense transfers, joint account transactions, shared tax filings, and insurance policies naming each other as primary beneficiary. |
| PFL-STATUTOR-04 | pfl_data_discrepancy_and_misrepresentation | high | Discrepancy in Cohabitation Dates or Addresses Between IMM 5409, Express Entry Profile, CRA Tax Returns, and Identity Documents | discovery | https://laws-lois.justice.gc.ca/eng/regulations/SOR-2002-227/section-4.html | Submit a detailed, sworn affidavit clarifying all address/marital status timelines across CRA, provincial registries, and immigration forms; provide official CRA tax marital status adjustment notices or formal explanation of administrative delays in updating government IDs. |

## Failure Mode Details

### PFL-STATUTOR-01: IMM 5409 Statutory Declaration Missing Notarization, Official Stamp, or Valid Solemnization Signature
- **Authority Classification:** discovery
- **Description:** The submitted IMM 5409 form lacks solemn declaration before a qualified official (Notary Public, Commissioner for Oaths, or Justice of the Peace), relies solely on unverified electronic signatures, or fails to include the commissioner's official seal and jurisdiction details. Under IRCC completeness guidelines, an un-notarized or improperly solemnized IMM 5409 renders the common-law declaration legally invalid, leading to application rejection at the completeness check or issuance of a Procedural Fairness Letter (PFL).
- **Affected Fields:** imm5409_solemn_declaration_signature, imm5409_commissioner_stamp, imm5409_declaration_date, imm5409_deponent_signatures
- **Remediation Hypothesis:** Re-execute IMM 5409 in the presence of an authorized Notary Public or Commissioner for Oaths who must affix their official seal, commission expiration date, and signature. Submit a letter of explanation and sworn affidavit confirming proper execution.
- **Supporting Excerpt (Online):** The form IMM 5409 must be completed and signed by both partners and solemnized (signed and stamped) in front of a Commissioner for Oaths, Notary Public, or Justice of the Peace. Handwritten signatures and original official commission stamps/seals are required.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-STATUTOR-02: Failure to Demonstrate 12 Consecutive Months of Continuous Cohabitation Prior to Application Submission
- **Authority Classification:** discovery
- **Description:** The applicant claims common-law status but supporting documentary evidence (leases, utility bills, address history) shows gaps in cohabitation, separate living arrangements, or a total continuous living duration of less than 12 months prior to submitting the e-APR. IRCC guidelines strictly enforce the requirement of 12 consecutive months of uninterrupted cohabitation in a conjugal relationship under IRPR section 1(1). Unexplained separations or premature submissions trigger a PFL or immediate refusal.
- **Affected Fields:** imm5409_cohabitation_start_date, imm5409_cohabitation_end_date, express_entry_personal_history_address, proof_of_cohabitation_dates
- **Remediation Hypothesis:** Submit a continuous month-by-month residential chronology covering the full 12-month period, including employer travel letters or travel itineraries to explain short temporary absences, along with additional concurrent evidence (e.g. government correspondence, rental receipts, joint utilities) proving unbroken shared living.
- **Supporting Excerpt (Online):** A common-law partner has been living with you for at least 12 consecutive months, meaning you’ve been living together continuously for one year, without any long periods apart. If either of you left your home it was for family obligations or work travel.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-STATUTOR-03: Lack of Joint Financial Arrangements or Shared Financial Interdependence Evidence
- **Authority Classification:** discovery
- **Description:** The application includes IMM 5409 and proof of a shared address but fails to provide documentary proof showing commingling of financial affairs, such as joint bank accounts, joint credit cards, shared utility bills, or designation as insurance/pension beneficiaries. IRCC officers evaluate financial interdependence to confirm a genuine conjugal relationship; absence of shared financial ties raises suspicion of a non-genuine relationship or convenience partnership under IRPR section 4.
- **Affected Fields:** imm5409_section_2_financial_arrangements, joint_bank_statement_proof, shared_utility_bills_proof, insurance_beneficiary_proof
- **Remediation Hypothesis:** Provide comprehensive documentary proof of financial integration over the full 12-month cohabitation period, such as joint bank statements showing regular shared household expense transfers, joint account transactions, shared tax filings, and insurance policies naming each other as primary beneficiary.
- **Supporting Excerpt (Online):** Items that can be used as proof of a common-law relationship include: shared ownership of residential property, joint leases or rental agreements, bills for shared utility accounts (gas, electricity, telephone), and important documents for both showing the same address.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-STATUTOR-04: Discrepancy in Cohabitation Dates or Addresses Between IMM 5409, Express Entry Profile, CRA Tax Returns, and Identity Documents
- **Authority Classification:** discovery
- **Description:** Inconsistencies exist between the cohabitation start date listed on IMM 5409, the address history reported in the Express Entry personal history section, CRA marital/address status filings, and driver's licenses/official IDs. Divergent address histories or conflicting marital status declarations (e.g. reporting 'Single' on CRA tax returns during the claimed cohabitation period) trigger PFLs citing credibility concerns or potential misrepresentation under A40.
- **Affected Fields:** imm5409_cohabitation_dates, express_entry_address_history, cra_tax_marital_status, drivers_license_address
- **Remediation Hypothesis:** Submit a detailed, sworn affidavit clarifying all address/marital status timelines across CRA, provincial registries, and immigration forms; provide official CRA tax marital status adjustment notices or formal explanation of administrative delays in updating government IDs.
- **Supporting Excerpt (Online):** A foreign national shall not be considered a common-law partner if the relationship is not genuine or was entered into primarily for the purpose of acquiring any status or privilege under the Act.
- **Local Corpus Evidence:** Not verified in local corpus
