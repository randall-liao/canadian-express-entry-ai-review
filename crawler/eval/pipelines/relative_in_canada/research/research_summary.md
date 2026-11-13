# Research Summary: relative_in_canada

## Executive Summary

Live research into IRCC Express Entry requirements and operational instructions for claiming Comprehensive Ranking System (CRS) points for a relative in Canada (sibling) reveals four primary failure modes: incomplete birth certificate chains failing to establish shared parentage, missing or partial Canadian status documents (such as missing the back side of a PR card), outdated or insufficient evidence of current physical residence in Canada, and missing legal marriage/adoption documentation required to prove step-sibling or adoptive relationships.

## Identified Failure Modes

| ID | Category | Severity | Title | Authority Classification | Citation | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| PFL-RELATIVE-01 | pfl_insufficient_proof_relationship | critical | Missing or Incomplete Birth Certificates Proving Shared Parentage | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/common-supporting-documents.html | Obtain and submit official long-form birth certificates for both the applicant and the sibling showing common parent names. If official records are unavailable, submit a civil status non-availability certificate alongside secondary evidence (family registry, baptismal record) and a sworn affidavit. |
| PFL-RELATIVE-02 | pfl_invalid_status_proof | critical | Incomplete or Expired Proof of Relative's Canadian Citizenship or PR Status | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents.html | Provide a complete scan of both sides of the relative's PR card, Canadian passport bio-page, or Canadian Citizenship Certificate. If PR card is expired, include IMM 5292/IMM 5688 Confirmation of Permanent Residence along with PR card renewal submission receipt. |
| PFL-RELATIVE-03 | pfl_insufficient_proof_residence | high | Insufficient or Outdated Evidence of Relative's Physical Residence in Canada | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/common-supporting-documents.html | Submit multiple recent (within 6 months) proofs of Canadian residence, such as utility bills (electricity, water, gas), active residential lease agreement, current CRA Notice of Assessment, and bank statement showing active local transactions at the Canadian address. |
| PFL-RELATIVE-04 | pfl_unverified_family_link | critical | Unverified Step-Sibling or Adoptive Relationship Link Without Supporting Legal Records | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm0802.html | Provide the complete chain of legal documentation, including legal adoption certificates issued by recognized authorities or parents' marriage certificates and divorce decrees establishing the valid step-parent or adoptive relationship. |

## Failure Mode Details

### PFL-RELATIVE-01: Missing or Incomplete Birth Certificates Proving Shared Parentage
- **Authority Classification:** discovery
- **Description:** The applicant claims CRS points for a sibling in Canada but submits short-form birth certificates that omit parental details or fails to provide birth certificates for both the applicant and the sibling. IRCC completeness guidelines require long-form birth certificates for both individuals that explicitly show at least one common parent.
- **Affected Fields:** proof_of_relationship, applicant_birth_certificate, sibling_birth_certificate, crs_points_sibling_in_canada
- **Remediation Hypothesis:** Obtain and submit official long-form birth certificates for both the applicant and the sibling showing common parent names. If official records are unavailable, submit a civil status non-availability certificate alongside secondary evidence (family registry, baptismal record) and a sworn affidavit.
- **Supporting Excerpt (Online):** To prove a relationship to a relative in Canada, birth certificates or legal documents showing common parents must be provided. Both the applicant's and the relative's long-form birth certificates indicating parent names are required.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-RELATIVE-02: Incomplete or Expired Proof of Relative's Canadian Citizenship or PR Status
- **Authority Classification:** discovery
- **Description:** The applicant submits only the front side of the relative's Permanent Resident (PR) card, an expired PR card without evidence of renewal, or temporary resident documents (such as a study/work permit). IRCC requires conclusive proof of permanent resident or citizenship status.
- **Affected Fields:** relative_status_proof, pr_card_copy, canadian_citizenship_proof, relative_status_in_canada
- **Remediation Hypothesis:** Provide a complete scan of both sides of the relative's PR card, Canadian passport bio-page, or Canadian Citizenship Certificate. If PR card is expired, include IMM 5292/IMM 5688 Confirmation of Permanent Residence along with PR card renewal submission receipt.
- **Supporting Excerpt (Online):** To prove status, submit a copy of the relative's Canadian citizenship certificate/card, Canadian passport, or permanent resident card (both front and back).
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-RELATIVE-03: Insufficient or Outdated Evidence of Relative's Physical Residence in Canada
- **Authority Classification:** discovery
- **Description:** The applicant provides outdated address documents (older than 6 months), driver's license only, or sole affidavits without primary objective proof that the Canadian relative is currently physically residing in Canada.
- **Affected Fields:** relative_proof_of_residence, utility_bills, notice_of_assessment, residential_address_proof
- **Remediation Hypothesis:** Submit multiple recent (within 6 months) proofs of Canadian residence, such as utility bills (electricity, water, gas), active residential lease agreement, current CRA Notice of Assessment, and bank statement showing active local transactions at the Canadian address.
- **Supporting Excerpt (Online):** Proof of residency must demonstrate that the relative is currently living in Canada. Acceptable evidence includes recent utility bills, lease agreements, bank statements, or CRA Notice of Assessment showing the Canadian address.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-RELATIVE-04: Unverified Step-Sibling or Adoptive Relationship Link Without Supporting Legal Records
- **Authority Classification:** discovery
- **Description:** The applicant claims points for a step-sibling or adopted sibling but fails to provide parental marriage certificates, divorce records, or formal court adoption orders that establish the legal chain linking the applicant and relative.
- **Affected Fields:** step_sibling_proof, adoption_certificate, parental_marriage_certificate, relationship_chain_docs
- **Remediation Hypothesis:** Provide the complete chain of legal documentation, including legal adoption certificates issued by recognized authorities or parents' marriage certificates and divorce decrees establishing the valid step-parent or adoptive relationship.
- **Supporting Excerpt (Online):** For step-siblings or adoptive siblings, legal adoption papers or marriage certificates linking parents are required to demonstrate the biological or legal relationship chain.
- **Local Corpus Evidence:** Not verified in local corpus
