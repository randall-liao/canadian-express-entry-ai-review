# Research Summary: digital_photo

## Executive Summary

Live research on IRCC digital photo specifications for Express Entry and Permanent Residence applications reveals that non-compliant photos account for a major portion of application returns and processing delays. Primary rejection triggers include dimensions violating 50x70mm ratio or pixel range limits (715x1000 to 2000x2800 px), photos older than 6 months or lacking proof of date taken, improper chin-to-crown framing outside 31-36mm, and image defects such as background/facial shadows, glare, or non-white backgrounds.

## Identified Failure Modes

| ID | Category | Severity | Title | Authority Classification | Citation | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| PFL-DIGITAL_-01 | pfl_spec_non_compliance | critical | Photo Dimensions and File Specification Non-Compliance (< 50x70mm or Out of Pixel Range) | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents/card/photos.html | Obtain a original professional digital photo in JPEG format sized between 715 x 1000 and 2000 x 2800 pixels and under 4 MB, ensuring aspect ratio strictly reflects 50 mm width by 70 mm height. |
| PFL-DIGITAL_-02 | pfl_outdated_document | critical | Photo Recency Non-Compliance (Date Taken Older Than 6 Months) | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents/card/photos.html | Re-take a new digital photo at a professional studio within 6 months of submission and upload the photographer receipt/studio invoice confirming studio details and exact date photo was taken. |
| PFL-DIGITAL_-03 | pfl_incorrect_framing | high | Incorrect Chin-to-Crown Frame Size and Face Composition | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents/card/photos.html | Re-shoot photo with a commercial photographer providing the official IRCC PR photograph specification guide to ensure chin-to-crown measurement occupies 31 mm to 36 mm height with head centered. |
| PFL-DIGITAL_-04 | pfl_lighting_background_defect | high | Shadow, Glare, or Non-White Background Defect | discovery | https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents/card/photos.html | Provide a replacement studio digital photo shot against a solid, plain white, untextured background using balanced studio flash diffusion to eliminate shadows and glass glare. |

## Failure Mode Details

### PFL-DIGITAL_-01: Photo Dimensions and File Specification Non-Compliance (< 50x70mm or Out of Pixel Range)
- **Authority Classification:** discovery
- **Description:** The uploaded digital photo fails to meet physical aspect ratio specifications (equivalent to 50 mm wide x 70 mm high) or digital parameters, such as pixel dimensions outside the mandatory 715 x 1000 to 2000 x 2800 pixels range or a file size exceeding 4 MB. Non-compliant digital dimensions trigger automated portal validation warnings or rejection at completeness check.
- **Affected Fields:** photo_dimensions, pixel_resolution, file_size
- **Remediation Hypothesis:** Obtain a original professional digital photo in JPEG format sized between 715 x 1000 and 2000 x 2800 pixels and under 4 MB, ensuring aspect ratio strictly reflects 50 mm width by 70 mm height.
- **Supporting Excerpt (Online):** We may return your photo if... the measurements are not between 715 × 1000 and 2000 × 2800 pixels... the file size is above 4 MB... it does not meet the photo requirements.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-DIGITAL_-02: Photo Recency Non-Compliance (Date Taken Older Than 6 Months)
- **Authority Classification:** discovery
- **Description:** The submitted photo was taken more than 6 months prior to application submission or fails to reflect the applicant's current appearance. Reusing outdated photos or submitting photos without the required photographer receipt/declaration showing date taken triggers a Procedural Fairness Letter (PFL) or photo resubmission request.
- **Affected Fields:** photo_date_taken, applicant_appearance_recency, photographer_receipt
- **Remediation Hypothesis:** Re-take a new digital photo at a professional studio within 6 months of submission and upload the photographer receipt/studio invoice confirming studio details and exact date photo was taken.
- **Supporting Excerpt (Online):** Upload a document that includes the information that would normally be listed on the back of the photo: the name and date of birth of the person in the photo, the date taken and the name and complete address of the photo studio, a confirmation from the photo studio (for example, a receipt).
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-DIGITAL_-03: Incorrect Chin-to-Crown Frame Size and Face Composition
- **Authority Classification:** discovery
- **Description:** The facial height in the image fails to meet the 31 mm to 36 mm (chin to crown) proportion requirement, or the applicant is not centered facing directly forward with neutral facial expression. Improper cropping or head size proportional errors cause biometric validation failure.
- **Affected Fields:** chin_to_crown_height, face_framing_position, facial_expression
- **Remediation Hypothesis:** Re-shoot photo with a commercial photographer providing the official IRCC PR photograph specification guide to ensure chin-to-crown measurement occupies 31 mm to 36 mm height with head centered.
- **Supporting Excerpt (Online):** The size of the head, from chin to crown, must be between 31 mm and 36 mm. Head and shoulders must be centered and squared to the camera with neutral expression.
- **Local Corpus Evidence:** Not verified in local corpus

### PFL-DIGITAL_-04: Shadow, Glare, or Non-White Background Defect
- **Authority Classification:** discovery
- **Description:** The photo contains dark background/facial shadows, flash reflections, glare on eyeglasses, or an off-white/patterned background. Facial shadows or reflections interfere with facial recognition processing and result in photo return.
- **Affected Fields:** background_color, lighting_quality, glare_shadows
- **Remediation Hypothesis:** Provide a replacement studio digital photo shot against a solid, plain white, untextured background using balanced studio flash diffusion to eliminate shadows and glass glare.
- **Supporting Excerpt (Online):** We may return your photo if it’s too dark, the background is not white, or there is too much glare in the photo. Photos must have uniform lighting with no shadows, glare or flash reflections.
- **Local Corpus Evidence:** Not verified in local corpus
