# Canadian Express Entry AI Review

> **Grounded, citable multi-agent guidance for Canadian Express Entry (e-APR post-ITA) applicants and immigration professionals.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![AGENTS.md Standard](https://img.shields.io/badge/Standard-AGENTS.md-green.svg)](AGENTS.md)
[![Publish Safe](https://img.shields.io/badge/Publish--Safe-Verified-success.svg)](#publish-safety--conformance)

**Canadian Express Entry AI Review** is an open-standard, multi-agent AI system designed to audit Canadian Express Entry permanent residence (e-APR) applications post-ITA. It verifies supporting documents, substantiates claimed Comprehensive Ranking System (CRS) points, screens edge-case IRCC policy rules, and exports redacted remediation packets for professional legal review.

---

## 🌟 Key Features

* **100% Grounded Citations**: Every immigration rule, document requirement, and CRS point formula is verbatim-grounded in an authoritative local corpus (`corpus/index.db`) compiled from IRCC Operational Bulletins, Program Delivery Instructions (PDIs), IRPA, and IRPR.
* **Strict Local PII Containment**: All applicant personal identifiable information (PII) stays strictly local inside git-ignored candidate vaults (`personal/candidates/<id>/`). Zero applicant data leaks into public claim strings or stdout envelopes.
* **Open `AGENTS.md` Standard**: Single source of truth specification for instructions, roles, contracts, and fail-closed grounding rules across all major AI CLI runtimes.
* **4-Stage Review Workflow**: Linear operational pipeline covering Candidate Setup, Document Extractions & Confirmations, Grounded CRS Audits & Screening, and Private Remediation Packet Export.
* **Edge-Case Policy Screening**: Specialized screening gates for Medical Examination Confirmations (MEC), NOC Work Experience Duty Matching, and Study Permit / Canadian Education Eligibility.
* **Multi-CLI Compatibility**: Out-of-the-box support for GitHub Copilot, Claude Code, OpenAI Codex, Cursor, Windsurf, and Antigravity.
* **Publish-Safety Verification**: Built-in stdlib checker (`scripts/check_publish_safe.py`) ensuring zero secrets, absolute machine paths, or private vault artifacts are committed.

---

## 🚀 Quickstart (30 Seconds)

### 1. Prerequisites & Installation

Ensure Python 3.11 is installed. Clone the repository and set up the environment:

```bash
git clone https://github.com/randall-liao/canadian-express-entry-ai-review.git
cd canadian-express-entry-ai-review

# Required for OCR of scanned documents on Debian/Ubuntu
sudo apt-get install tesseract-ocr

# Create the Poetry environment with Python 3.11
poetry env use "$(uv python find 3.11)"

# Install the package plus document extraction and OCR support
poetry install -E doc-extract -E ocr
```

### 2. Run Preflight Doctor Check

Verify that local dependencies, OCR tools, and corpus index are healthy:

```bash
poetry run corpus-crawler --json doctor
```

### 3. Start a Review with GitHub Copilot

Download the pinned Copilot SDK runtime, start Copilot at the repository root,
and state what you want reviewed:

```bash
poetry run python -m copilot download-runtime
copilot
```

Then send:

```text
I want to review my passport for my Express Entry application.
```

The root agent follows [`AGENTS.md`](AGENTS.md), determines the local path and
document type, imports into a git-ignored candidate vault, asks you to confirm
uncertain extracted fields, runs corpus-grounded review and applicable
screening, and generates private remediation or a redacted review packet.
Source documents, applicant facts, and extracted fields remain local.

### 4. Run Multi-CLI Conformance Gate

Verify system integrity across all CLI adapters and safety rules:

```bash
.venv/bin/python scripts/run_multi_cli_conformance.py
```

---

## 🏗️ Multi-Agent Architecture

The system partitions document verification and CRS auditing responsibilities into **4 specialized agent roles**, governed by portable Markdown skill specifications under `skills/`:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Lead Review Coordinator                          │
│   • Manages candidate setup, onboarding, and workflow delegation        │
│   • Executes top-level vault & checklist CLI orchestration              │
└──────────────┬──────────────────────────┬───────────────────────────────┘
               │                          │
               ▼                          ▼
┌───────────────────────────────┐  ┌──────────────────────────────────────┐
│    Document Review Agent      │  │          CRS Auditor Agent           │
│ • Verifies mandatory e-APR    │  │ • Substantiates claimed CRS points   │
│   supporting documents        │  │   (Human Capital, Spouse, Transfer)  │
│ • Validates passports, ECA,   │  │ • Evaluates policy rules against     │
│   language, work letters      │  │   confirmed document extractions     │
└──────────────┬────────────────┘  └──────────────────┬───────────────────┘
               │                                      │
               └──────────────────┬───────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Remediation Exporter                           │
│   • Generates private, actionable remediation gap checklists            │
│   • Exports redacted, shareable RCIC / Lawyer review packets            │
└─────────────────────────────────────────────────────────────────────────┘
```

1. **Lead Review Coordinator**: Manages applicant onboarding, initializes candidate vaults, loads factor profiles, generates Layer-1 checklists, and summarizes results.
2. **Document Review Agent**: Audits mandatory supporting documents (passports, language test reports, ECAs, work reference letters, police certificates, medicals) against grounded IRCC criteria.
3. **CRS Auditor Agent**: Evaluates claimed CRS points across Core Human Capital, Spouse/Partner, Skill Transferability, and Additional Points factors using deterministic rule registries.
4. **Remediation Exporter**: Compiles private remediation checklists for gaps or AT-RISK items and exports redacted review packets safe for external RCIC / lawyer consultation.

---

## 📖 Open `AGENTS.md` Standard

This repository uses [`AGENTS.md`](./AGENTS.md) at the repository root as its canonical specification. `AGENTS.md` defines:

* **System Invariants**: Grounding rules, PII isolation rules, and answer JSON schemas.
* **CLI Tool Contracts**: Standardized 5-key JSON envelope (`schema_version`, `ok`, `command`, `result`, `error`).
* **4-Stage Workflow**: Standardized command sequence for full document reviews.
* **Skill Interfaces**: Path mappings for domain skills under `skills/`.

Every supported AI CLI tool reads `AGENTS.md` directly or through a thin adapter pointer.

---

## 💻 Multi-CLI Setup Instructions

Set up your preferred AI CLI or IDE assistant using the repository's native adapter configurations:

| AI CLI / IDE | Adapter Path | Setup Action |
|---|---|---|
| **Claude Code** | `CLAUDE.md` | Automatic on startup when opening repo root in `claude`. |
| **GitHub Copilot** | `.github/copilot-instructions.md` | Automatic when working in GitHub Copilot Chat or CLI. |
| **OpenAI Codex** | `.codex/AGENTS.md` | Read automatically by Codex CLI. |
| **Cursor IDE** | `.cursor/rules/agents.mdc` | Applied automatically (`alwaysApply: true`) across workspace files. |
| **Windsurf** | `.windsurfrules` | Loaded automatically by Cascade agent. |
| **Antigravity** | `AGENTS.md` | Loaded via the root specification. |

---

## 🛠️ Installation & Execution Options

You can invoke the underlying CLI tools via multiple runner patterns:

### Option A: `uv` Execution (Fast & Isolated)
```bash
uv run corpus-crawler --json <command> [args...]
```

### Option B: Virtualenv Python Interpreter
```bash
.venv/bin/python -m crawler.cli --json <command> [args...]
# or via installed entrypoint:
.venv/bin/corpus-crawler --json <command> [args...]
```

### Option C: Poetry
```bash
poetry run corpus-crawler --json <command> [args...]
```

---

## 📋 4-Stage Operational Workflow Example

Below is the standard 4-stage operational workflow executed by agents and applicants:

### Stage 1: Candidate Setup & Ingestion
```bash
# Initialize candidate vault
corpus-crawler --json vault init --candidate cand_001 --label "John Doe e-APR"

# Load Express Entry profile parameters
corpus-crawler --json vault profile set --factor-file personal.example/profile.yaml --candidate cand_001

# Record ITA round cutoff details
corpus-crawler --json vault ita set --round "Round 280" --cutoff 525 --program "Express Entry" --candidate cand_001

# Import candidate documents
corpus-crawler --json vault import path/to/passport.pdf --doc-type passport --candidate cand_001

# Generate Layer-1 document checklist
corpus-crawler --json checklist --profile personal/candidates/cand_001 --db corpus/index.db
```

### Stage 2: Document Extraction & Field Confirmation
```bash
# Run automated document field extractions
corpus-crawler --json vault extract --candidate cand_001

# Run preflight quality & dependency diagnostics
corpus-crawler --json doctor --candidate cand_001

# Inspect pending extracted fields
corpus-crawler --json vault fields --candidate cand_001 --status pending

# Confirm or correct an extracted value
corpus-crawler --json vault confirm --value-id val_passport_expiry --decision confirm --candidate cand_001
```

### Stage 3: Grounded Audit & Policy Screening
```bash
# Execute full CRS score substantiation audit
corpus-crawler --json vault audit --all --candidate cand_001 --db corpus/index.db

# Run Medical Examination Screening (MEC)
corpus-crawler --json vault screen-mec --candidate cand_001 --db corpus/index.db

# Run NOC Work Experience Review
corpus-crawler --json vault noc-review --candidate cand_001 --db corpus/index.db

# Run Study Permit & Canadian Education Review
corpus-crawler --json vault study-review --candidate cand_001 --db corpus/index.db
```

### Stage 4: Remediation & Review Packet Export
```bash
# Generate private remediation guidance
corpus-crawler --json vault remediate --candidate cand_001 --db corpus/index.db

# Export redacted review packet for RCIC / legal consultation
corpus-crawler --json vault review-packet --candidate cand_001 --db corpus/index.db
```

---

## 🛡️ Publish Safety & Conformance

To guarantee that no private candidate data, machine-specific paths, or secret tokens are published to public repositories, run the stdlib publish-safety checker:

```bash
.venv/bin/python scripts/check_publish_safe.py
```

To run the complete system conformance suite:

```bash
.venv/bin/python scripts/run_conformance.py
```

---

## Contributing and repository access

Open pull requests against `main`. Changes require a code-owner review, and new
commits dismiss earlier approvals. Resolve review conversations before merging.
Force-pushes and branch deletion are disabled; the repository owner retains an
administrator bypass for solo maintenance. GitHub Actions uses read-only default
token permissions, and workflows from external contributors require approval.
Never include applicant documents, vaults, credentials, or local corpora in a pull request.

### Initial snapshot verification

The initial public snapshot passes the publication-safety checker. The full Python
test suite currently stops during collection: two conformance tests import the
undeclared `tomli` dependency, and the legacy `judge_group_c` and `parallel_judge`
modules import removed helpers from the retired `agent_improvement_loop` module.
These are known issues in this snapshot; a passing full test suite is not claimed.
`TEST_REPORT.md` records an earlier evaluation run, not a passing test result for
this initial public release.

---

## 📄 License & Legal Disclaimer

* **Software License**: Distributed under the [MIT License](LICENSE).
* **Attribution**: See [NOTICE](NOTICE) for third-party citations and corpus source attribution.
* **Disclaimer**: This system provides **substantiation screening**, NOT legal advice. It does not decide cases or guarantee IRCC application outcomes. Always consult a licensed Regulated Canadian Immigration Consultant (RCIC) or immigration lawyer for legal counsel.
