# PR Review Agents — Step-by-Step Applicant User Guide

> **An in-depth, step-by-step guide for Canadian Express Entry (e-APR post-ITA) applicants using multi-agent AI tools for document verification, CRS score auditing, and remediation packet generation.**

---

## 📌 Table of Contents

1. [Executive Overview & Onboarding](#1-executive-overview--onboarding)
2. [Prerequisites & Environment Setup](#2-prerequisites--environment-setup)
3. [Stage 1: Candidate Setup & Document Ingestion](#3-stage-1-candidate-setup--document-ingestion)
4. [Stage 2: Document Extractions & Field Confirmations](#4-stage-2-document-extractions--field-confirmations)
5. [Stage 3: Grounded CRS Audits & Edge-Case Policy Screening](#5-stage-3-grounded-crs-audits--edge-case-policy-screening)
6. [Stage 4: Private Remediation & Redacted RCIC Review Packet Exports](#6-stage-4-private-remediation--redacted-rcic-review-packet-exports)
7. [Troubleshooting & Best Practices](#7-troubleshooting--best-practices)

---

## 1. Executive Overview & Onboarding

### Purpose
Submitting an Express Entry electronic Application for Permanent Residence (e-APR) after receiving an Invitation to Apply (ITA) is a critical step. Document mismatches, expired language tests, missing reference letter duties, or unverified CRS points can lead to application refusal under A11.2 or section 16 of the Immigration and Refugee Protection Act (IRPA).

`PR Review Agents` provides an automated, grounded document review assistant that:
* Audits every document against official IRCC Operational Bulletins and Program Delivery Instructions (PDIs).
* Verifies whether claimed CRS points are substantiated by confirmed document extractions.
* Highlights potential risks (e.g. NOC duty mismatches, study permit work restrictions, medical examination requirements).
* Compiles private, actionable remediation checklists and generates redacted review packets for professional consultation.

### Strict Local Privacy Guarantee
All personal data (names, dates of birth, passport numbers, work history, language scores) is treated as strictly confidential Personal Identifiable Information (PII).
* **Local Vault Isolation**: PII is written exclusively to git-ignored SQLite candidate vaults under `personal/candidates/<id>/`.
* **Zero PII Leakage**: Generated public claims, audit summary objects, and review packets strip or redact applicant personal facts. Personal details are confined to `basis[]` fields and local vault databases.

### Legal Framing & Review Disclaimer
This tool provides **substantiation screening**, not legal representation or legal advice. It evaluates whether claimed points and uploaded documents meet IRCC requirements. It does not guarantee IRCC approval. Always review findings with a licensed Regulated Canadian Immigration Consultant (RCIC) or immigration lawyer.

---

## 2. Prerequisites & Environment Setup

### 2.1 Python Environment & Tooling
Ensure Python 3.10 or higher is installed on your system.

```bash
# Clone repository
git clone https://github.com/your-org/pr-review-agents.git
cd pr-review-agents

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install package in editable mode
pip install -e .
```

### 2.2 Template Factor Profile
Copy the example factor profile from `personal.example/profile.yaml` to set up your applicant parameters:

```bash
mkdir -p personal
cp personal.example/profile.yaml personal/my_profile.yaml
```

Edit `personal/my_profile.yaml` with your details (e.g. age, education credentials, language scores, work experience years, marital status, Canadian study/work details).

---

## 3. Stage 1: Candidate Setup & Document Ingestion

### Step 1.1: Initialize the Candidate Vault
Create a isolated local vault for your application:

```bash
corpus-crawler --json vault init --candidate cand_001 --label "Applicant e-APR Review"
```

*Output*: Creates SQLite database `personal/candidates/cand_001/vault.sqlite` and directory structure.

### Step 1.2: Set Candidate Profile Parameters
Load your factor profile into the vault:

```bash
corpus-crawler --json vault profile set --factor-file personal/my_profile.yaml --candidate cand_001
```

### Step 1.3: Record ITA Details
Record your Invitation to Apply (ITA) details, including draw date, round number, program type, and cutoff score:

```bash
corpus-crawler --json vault ita set \
  --round "Round 280" \
  --cutoff 525 \
  --program "Express Entry - Federal Skilled Worker" \
  --candidate cand_001
```

### Step 1.4: Import Applicant Supporting Documents
Import all PDF or image supporting documents (passports, language test reports, ECA reports, employment reference letters, police certificates, medical receipts, proof of funds):

```bash
corpus-crawler --json vault import /path/to/passport.pdf --doc-type passport --candidate cand_001
corpus-crawler --json vault import /path/to/ielts_results.pdf --doc-type language_test --candidate cand_001
corpus-crawler --json vault import /path/to/wes_eca.pdf --doc-type eca --candidate cand_001
corpus-crawler --json vault import /path/to/employment_letter.pdf --doc-type reference_letter --candidate cand_001
```

### Step 1.5: Generate Layer-1 Document Checklist
Generate a personalized document checklist grounded against IRCC requirements for your profile:

```bash
corpus-crawler --json checklist --profile personal/candidates/cand_001 --db corpus/index.db
```

---

## 4. Stage 2: Document Extractions & Field Confirmations

### Step 2.1: Automated Field Extraction
Execute automated OCR and text parsing across imported candidate documents:

```bash
corpus-crawler --json vault extract --candidate cand_001
```

This extracts critical fields (e.g., expiry dates, document numbers, score breakdown, job duties, wage rates, hours worked per week).

### Step 2.2: Preflight Health & Scan Quality Check
Run preflight diagnostics to ensure document scan quality and system dependencies are sufficient:

```bash
corpus-crawler --json doctor --candidate cand_001
```

Inspect output for warnings regarding low DPI scans, unreadable pages, or missing OCR drivers.

### Step 2.3: Inspect Pending Extracted Fields
List extracted fields awaiting applicant review and confirmation:

```bash
corpus-crawler --json vault fields --candidate cand_001 --status pending
```

*Note*: Detailed field values print to stderr for human verification while stdout receives a PII-safe summary.

### Step 2.4: Human Confirmation Workflow
Verify each extracted field against your physical document. Confirm correct values or supply corrections:

```bash
# Confirm a correct value:
corpus-crawler --json vault confirm --value-id val_passport_expiry --decision confirm --candidate cand_001

# Correct an incorrectly extracted value:
corpus-crawler --json vault confirm --value-id val_ielts_speaking --decision correct --value "7.5" --candidate cand_001
```

---

## 5. Stage 3: Grounded CRS Audits & Edge-Case Policy Screening

### Step 5.1: Execute Complete CRS Score Audit
Run a comprehensive CRS score substantiation audit across all claimed point categories:

```bash
corpus-crawler --json vault audit --all --candidate cand_001 --db corpus/index.db
```

#### Understanding Audit Verdicts

The auditor categorizes each CRS factor into one of 4 strict verdicts:

* 🟢 **`SUBSTANTIATED`**: Claimed points are fully backed by confirmed document extractions and meet all grounded IRCC rules.
* 🟡 **`AT-RISK`**: Points require human or professional review (e.g., subjective job duty matching, expiring documents, or missing officer discretion elements).
* 🔴 **`GAP`**: Required supporting proof is missing, invalid, expired, or below claimed thresholds.
* ⚪ **`N/A`**: Factor not claimed or not applicable to your profile.

### Step 5.2: Medical Examination Screening (MEC)
Screen medical examination requirements, in-Canada temporary public policy exemptions, and IME upfront receipt validity:

```bash
corpus-crawler --json vault screen-mec --candidate cand_001 --db corpus/index.db
```

### Step 5.3: NOC Work Experience Duty Review
Perform semantic duty matching between your employment reference letter duties and official National Occupational Classification (NOC) lead statements:

```bash
corpus-crawler --json vault noc-review --candidate cand_001 --db corpus/index.db
```

### Step 5.4: Study Permit & Canadian Education Review
Verify Designated Learning Institution (DLI) eligibility, PGWP status, and full-time study requirements for claimed Canadian educational points:

```bash
corpus-crawler --json vault study-review --candidate cand_001 --db corpus/index.db
```

---

## 6. Stage 4: Private Remediation & Redacted RCIC Review Packet Exports

### Step 6.1: Generate Private Remediation Checklist
Compile an actionable, private remediation guide for any document gaps, missing fields, or AT-RISK items:

```bash
corpus-crawler --json vault remediate --candidate cand_001 --db corpus/index.db
```

*Output*: Generates a detailed step-by-step remediation document saved locally in your candidate vault directory (`personal/candidates/cand_001/output/remediation/`).

### Step 6.2: Export Redacted Professional Review Packet
Export a shareable review packet for your Regulated Canadian Immigration Consultant (RCIC) or immigration lawyer:

```bash
corpus-crawler --json vault review-packet --candidate cand_001 --db corpus/index.db
```

*Key Security Feature*: The generated review packet strips all PII (applicant name, dates of birth, document serial numbers) while preserving factor scores, rule citations, and audit evidence hashes.

---

## 7. Troubleshooting & Best Practices

### Common Issue 1: OCR / Unreadable Document Scans
* **Symptom**: `doctor` or `extract` reports low text extraction confidence or unreadable PDF pages.
* **Resolution**: Re-scan your document at 300+ DPI in high contrast, or supply manual field confirmations using `corpus-crawler --json vault confirm`.

### Common Issue 2: Grounding Gate Refusal
* **Symptom**: `ground` command returns `result.verdict == "fail"` with `quote_not_in_chunk`.
* **Resolution**: Ensure quotes in claims are copied verbatim from corpus search chunks. Do not paraphrase IRCC rule text inside quotes.

### Common Issue 3: Publish-Safety Check Failure
* **Symptom**: Running `scripts/check_publish_safe.py` flags an absolute path or secret.
* **Resolution**: Remove absolute paths or local environment references. Ensure candidate vault files remain strictly inside `personal/` (which is git-ignored).

---

## 💡 Summary & Final Checklist Before e-APR Submission

1. [ ] Candidate vault initialized and profile parameters loaded.
2. [ ] All supporting document fields extracted and 100% human-confirmed.
3. [ ] CRS audit completed with zero `GAP` verdicts on claimed points.
4. [ ] MEC, NOC, and Study Permit screenings reviewed.
5. [ ] Private remediation checklist items addressed.
6. [ ] Redacted review packet exported and reviewed with your RCIC / Lawyer.
