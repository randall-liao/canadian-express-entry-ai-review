# Research Summary: certified_translation

## Executive Summary

IRCC requires strict compliance for non-English and non-French supporting documents submitted in Express Entry and permanent residence applications. Mandatory standards mandate that translations must be completed by a certified translator in good standing (bearing their official stamp, seal, and registration number) or accompanied by a sworn translator affidavit executed before an authorized commissioner of oaths. Common failure modes causing application rejections, completeness check failures, or Procedural Fairness Letters (PFL) include using non-certified translators without an affidavit, relying on family members for translation, submitting incomplete page translations that omit stamps or annotations, and missing certified stamps or credentials.

## Identified Failure Modes

| ID | Category | Severity | Title | Authority Classification | Citation | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| PFL-CERTIFIE-01 | uncertified_translator_missing_affidavit | critical | Translation Completed by Uncertified Translator Without Sworn Affidavit | discovery | https://ircc.canada.ca/english/helpcentre/answer.asp?qnum=018&top=4 | Obtain a sworn affidavit signed by the non-certified translator in front of an authorized commissioner for taking affidavits, or re-translate the document using a certified translator affiliated with a recognized Canadian translation body. |
| PFL-CERTIFIE-02 | prohibited_family_translation | critical | Translation Prepared by Applicant or Family Member | discovery | https://ircc.canada.ca/english/helpcentre/answer.asp?qnum=039&top=4 | Re-translate the document using an independent third-party certified translator who has no personal or familial relationship to the applicant. |
| PFL-CERTIFIE-03 | incomplete_page_translation | high | Incomplete Translation Omitting Stamps, Marginalia, or Back Pages | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/common-supporting-documents.html | Obtain a comprehensive, unabridged translation covering all text, stamps, signatures, marginalia, and back-page notations present on the source document. |
| PFL-CERTIFIE-04 | missing_certified_seal_or_stamp | high | Missing Official Stamp or Seal of Recognized Certified Translator | discovery | https://ircc.canada.ca/english/helpcentre/answer.asp?qnum=040&top=4 | Provide a re-issued translation bearing the official seal/stamp and membership number of a certified translator in good standing with a recognized professional translation body. |

## Failure Mode Details

### PFL-CERTIFIE-01: Translation Completed by Uncertified Translator Without Sworn Affidavit
- **Authority Classification:** discovery
- **Description:** The submitted translation was performed by a translator who is not a certified member of a recognized provincial or national translation association, and the applicant failed to include a sworn affidavit from the translator attesting to language proficiency and accuracy executed before a commissioner authorized to administer oaths.
- **Affected Fields:** translator_certification_status, translator_affidavit, commissioner_of_oaths_seal
- **Remediation Hypothesis:** Obtain a sworn affidavit signed by the non-certified translator in front of an authorized commissioner for taking affidavits, or re-translate the document using a certified translator affiliated with a recognized Canadian translation body.
- **Supporting Excerpt (Online):** Unless we tell you otherwise, all supporting documents must be in English or French. If it is not in English or French, you must send it with: the English or French translation and an affidavit from the person who completed the translation and a certified photocopy of the original document
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-CERTIFIE-02: Translation Prepared by Applicant or Family Member
- **Authority Classification:** discovery
- **Description:** The document translation was completed by the applicant themselves or an immediate family member (e.g., spouse, parent, sibling, child), which violates explicit IRCC regulations even if the relative is a professional or certified translator.
- **Affected Fields:** translator_identity, relationship_to_applicant, translator_declaration
- **Remediation Hypothesis:** Re-translate the document using an independent third-party certified translator who has no personal or familial relationship to the applicant.
- **Supporting Excerpt (Online):** Yes. If your documents are not in English or French, you must send a translation from a certified translator with your application. We don’t accept translations by family members.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-CERTIFIE-03: Incomplete Translation Omitting Stamps, Marginalia, or Back Pages
- **Authority Classification:** discovery
- **Description:** The translated document omits portions of the original source document, such as government seals, registrar stamps, reverse-side endorsements, marginal notes, or attached pages, violating IRCC word-for-word completeness standards.
- **Affected Fields:** translated_text_completeness, translated_stamps_and_seals, page_count_match
- **Remediation Hypothesis:** Obtain a comprehensive, unabridged translation covering all text, stamps, signatures, marginalia, and back-page notations present on the source document.
- **Supporting Excerpt (Online):** Any document that is not in English or French must be accompanied by a certified translation. You must include a scan of both the original document and the complete translation.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-CERTIFIE-04: Missing Official Stamp or Seal of Recognized Certified Translator
- **Authority Classification:** discovery
- **Description:** The translation claims to be certified but lacks the official stamp, seal, or membership credentials of a recognized provincial or territorial organization of translators (such as ATIO, STIBC, OTTIAQ), preventing IRCC officers from verifying the translator's professional certification status.
- **Affected Fields:** certified_translator_stamp, translator_membership_number, professional_association_name
- **Remediation Hypothesis:** Provide a re-issued translation bearing the official seal/stamp and membership number of a certified translator in good standing with a recognized professional translation body.
- **Supporting Excerpt (Online):** An affidavit for a translation is a document that says the translation is a true and accurate version of the original text. The translator swears that their translation is a true and accurate representation of the contents of the original document.
- **Local Corpus Evidence:** Not verified in local corpus
