# Research Summary: proof_of_other_name

## Executive Summary

Online research into IRCC Express Entry operational guidelines and real-world failure cases reveals that 'proof_of_other_name' issues primarily stem from missing legal name change certificates, unauthenticated or unsealed court orders, name discrepancies between passports and educational/ECA records, and uncertified foreign language translations. When identity documents show variations or missing legal proofs, IRCC officers issue Procedural Fairness Letters (PFL) or reject applications under IRPR Section 10 completeness check.

## Identified Failure Modes

| ID | Category | Severity | Title | Authority Classification | Citation | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| PFL-POON_NAME-01 | pfl_incomplete_evidence | critical | Missing Official Government Legal Name Change Certificate | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/common-supporting-documents.html | Obtain an official legal name change certificate or government deed poll from the issuing provincial/state vital statistics agency, and submit it with a detailed Letter of Explanation mapping all legal name transitions. |
| PFL-POON_NAME-02 | pfl_invalid_format | critical | Court Order for Name Change Lacking Official Judicial Seal or Stamp | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/common-supporting-documents.html | Request a certified true copy bearing the raised official court seal or red/wet-ink stamp directly from the clerk of the issuing court, and submit it along with an official registry verification letter. |
| PFL-POON_NAME-03 | pfl_identity_discrepancy | high | Name Discrepancy Across Passport, ECA Report, and Educational Degrees | discovery | https://ircc.canada.ca/english/helpcentre/answer.asp?qnum=1535 | Execute a sworn 'One and the Same Person' affidavit before a Notary Public, obtain an official letter from the university registrar confirming applicant identity, and upload a comprehensive Letter of Explanation. |
| PFL-POON_NAME-04 | pfl_non_compliant_translation | high | Foreign Name Change Document Lacking Certified Translation or Translator Affidavit | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/common-supporting-documents.html | Obtain a certified translation performed by an accredited certified translator (or accompanied by a sworn translator affidavit) along with certified copies of the original foreign document. |

## Failure Mode Details

### PFL-POON_NAME-01: Missing Official Government Legal Name Change Certificate
- **Authority Classification:** discovery
- **Description:** The applicant declared a former name or legal name change in Express Entry personal history but uploaded only an informal self-declaration or marriage certificate without the mandatory government-issued legal name change certificate or official deed poll. IRCC requires official vital statistics or government-issued documentation to establish legal identity changes outside standard marriage registration.
- **Affected Fields:** proof_of_other_name, personal_history_names, given_name, family_name
- **Remediation Hypothesis:** Obtain an official legal name change certificate or government deed poll from the issuing provincial/state vital statistics agency, and submit it with a detailed Letter of Explanation mapping all legal name transitions.
- **Supporting Excerpt (Online):** If your current name is different from the name showing in other supporting documents... you must provide documentary proof of the name change (e.g., marriage certificate, legal name change certificate).
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-POON_NAME-02: Court Order for Name Change Lacking Official Judicial Seal or Stamp
- **Authority Classification:** discovery
- **Description:** The applicant submitted a plain, uncertified copy or photocopy of a court decree authorizing a name change that lacks an official raised court seal, registrar signature, or wet-ink verification stamp. IRCC officers verify document authenticity and reject unsealed court orders as unverified legal evidence during completeness assessment.
- **Affected Fields:** proof_of_other_name, court_order_document, issuing_court_seal
- **Remediation Hypothesis:** Request a certified true copy bearing the raised official court seal or red/wet-ink stamp directly from the clerk of the issuing court, and submit it along with an official registry verification letter.
- **Supporting Excerpt (Online):** You must submit official, clear, and legible copies of required documents... Documents confirming legal name change (if applicable) must be issued by a recognized authority.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-POON_NAME-03: Name Discrepancy Across Passport, ECA Report, and Educational Degrees
- **Authority Classification:** discovery
- **Description:** There is an unresolved variance between the name on the applicant's passport and their ECA report or university degree certificates (e.g., expanded initials, inverted surname/given name, or omitted middle names) without cross-linking proof in the 'proof_of_other_name' section. IRCC flags this as an unverified identity link, triggering a PFL or R10 rejection.
- **Affected Fields:** passport_full_name, eca_applicant_name, degree_certificate_name, proof_of_other_name
- **Remediation Hypothesis:** Execute a sworn 'One and the Same Person' affidavit before a Notary Public, obtain an official letter from the university registrar confirming applicant identity, and upload a comprehensive Letter of Explanation.
- **Supporting Excerpt (Online):** The aim is to provide enough evidence for IRCC to see that all your documents, regardless of name variation, refer to the same person... Include a letter of explanation outlining the reason for the name change and the supporting documents you have included.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-POON_NAME-04: Foreign Name Change Document Lacking Certified Translation or Translator Affidavit
- **Authority Classification:** discovery
- **Description:** The applicant uploaded a foreign legal name change certificate or municipal decree in a non-English/non-French language without an official certified translation or sworn translator affidavit as required under IRPR Section 10/11. Uncertified translations or plain self-translations result in application rejection for incompleteness.
- **Affected Fields:** proof_of_other_name, document_translation, translator_affidavit
- **Remediation Hypothesis:** Obtain a certified translation performed by an accredited certified translator (or accompanied by a sworn translator affidavit) along with certified copies of the original foreign document.
- **Supporting Excerpt (Online):** Any document that is not in English or French must be accompanied by the official translation and an affidavit from the person who completed the translation (if they are not a certified translator).
- **Local Corpus Evidence:** Not verified in local corpus
