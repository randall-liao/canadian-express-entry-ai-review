# Canadian Express Entry AI Review

> **Grounded, citable multi-agent guidance for Canadian Express Entry (e-APR post-ITA) applicants and immigration professionals.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![AGENTS.md Standard](https://img.shields.io/badge/Standard-AGENTS.md-green.svg)](AGENTS.md)
[![Publish Safe](https://img.shields.io/badge/Publish--Safe-Verified-success.svg)](#publish-safety--conformance)

**Canadian Express Entry AI Review** is an open-standard, multi-agent AI system designed to audit Canadian Express Entry permanent residence (e-APR) applications post-ITA. It verifies supporting documents, substantiates claimed Comprehensive Ranking System (CRS) points, screens edge-case IRCC policy rules, and exports redacted remediation packets for professional legal review.

> **Stale snapshot warning:** General policy, legal and NOC sources were captured on **2026-06-10–11**; DLI data has a separate **2026-07-16** upstream as-of date. These are not live policy updates. Verify each cited official source before relying on a result. See [snapshot cutoffs and refresh instructions](#bundled-corpus-and-refresh).

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

# Create the Poetry environment with Python 3.11
poetry env use "$(uv python find 3.11)"

# Install the core package; enough for offline search of the bundled index
poetry install
```

### 2. Search the Bundled Corpus Offline

The clone already contains `corpus/index.db`; no crawl or index build is required.
From the repository root, search immediately after installation:

```bash
poetry run corpus-crawler --json search "medical examination" --db corpus/index.db --limit 3
```

Search runs locally without API credentials or network access. Read `ok` first;
results carry source URLs and citation IDs, not a guarantee of current policy.

For applicant-document review, also install extraction and OCR support:

```bash
# Debian/Ubuntu: required only for OCR of scanned applicant documents
sudo apt-get install tesseract-ocr
poetry install -E doc-extract -E ocr
```

### 3. Run Preflight Doctor Check

Verify that local dependencies, OCR tools, and corpus index are healthy:

```bash
poetry run corpus-crawler --json doctor
```

### 4. Start a Review with GitHub Copilot

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

### 5. Run Multi-CLI Conformance Gate

Verify system integrity across all CLI adapters and safety rules:

```bash
.venv/bin/python scripts/run_multi_cli_conformance.py
```

---

## Bundled corpus and refresh

The checkout ships **1,878 public-source Markdown documents** and a ready-to-use
SQLite FTS5 index, [`corpus/index.db`](corpus/index.db). This is a curated subset,
not a complete archive of Canadian immigration policy or the NOC classification.

| Source family | Documents |
|---|---:|
| IRCC policy/guidance and Justice IRPA/IRPR legislation | 366 |
| Statistics Canada NOC 2021 Version 1.0 | 376 |
| IRCC designated learning institutions (DLI) | 1,136 |

The **742 non-DLI documents** have recorded `crawl_date` values from
`2026-06-10T23:27:24Z` through `2026-06-11T04:05:19Z`. DLI's
[`manifest.json`](corpus/dli/manifest.json) records `as_of` =
`2026-07-16T18:08:26Z`, derived from the upstream HTTP `Last-Modified` header;
DLI files use that same value as `crawl_date`, **not a fetch timestamp**.
The newest metadata date does not establish freshness for the rest of the corpus,
or even that a source was substantively reviewed on that date. DLI records cover
listed status at the snapshot date, not past designation or program-level PGWP
eligibility. Always check the live source linked in each document/result.

### Refresh one source family, then rebuild the index

There is **no automatic all-source updater**. Refresh is an audited maintenance
operation: acquire one family outside the shipped `corpus/`, quality-control it,
review the differences and coverage, deliberately promote approved files, then
reindex. A bounded crawl of one tree does not refresh the other families.

For example, from the repository root, stage an IRCC medical-tree crawl:

```bash
poetry install -E crawl
stage="$(mktemp -d)"
poetry run corpus-crawler --json crawl \
  --seed "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/publications-manuals/operational-bulletins-manuals/standard-requirements/medical-requirements.html" \
  --profile ircc --include "*medical*" --depth 2 --max-pages 40 \
  --source-type pdi --out "$stage/medical"
```

Crawling and live completeness checks require the optional `crawl` extra and its
Chromium/browser dependencies; see [`crawler/README.md`](crawler/README.md).
Adjust the seed, profile, scope and limits for the chosen family. **NOC and Justice
legislation need source-specific acquisition/curation** against their official
classification or consolidated laws; the IRCC example and `refresh-dli` do not
refresh them, and there is no dedicated NOC/legal refresh subcommand.

Follow [`crawler/QC_RUNBOOK.md`](crawler/QC_RUNBOOK.md): save a pre-QC copy, prune
only whole irrelevant sections without rewriting retained text, author one eval
contract per document, and confirm zero verbatim changes. Preserve each file's
`title`, `url`, `crawl_date` and publisher attribution (`label`); never make old
content appear fresh by changing its date. Then run the existing gates:

```bash
poetry run python -m crawler.eval_runner "$stage/medical"
poetry run corpus-crawler --json apply-verdicts "$stage/medical" --dry-run
poetry run corpus-crawler --json apply-verdicts "$stage/medical"
poetry run python -m crawler.eval_runner "$stage/medical"
poetry run corpus-crawler --json completeness "$stage/medical" --fraction 0.1
# Complete the runbook's sampled live-page audit and write its .check.json files
# before generating the report; fetching a sample alone is not a passing audit.
poetry run corpus-crawler --json report "$stage/medical"
```

Require passing evals and `result.verdict: "pass"` from the report. Review additions,
removals, retained coverage and source rights before replacing the corresponding
curated files under `corpus/`. Keep dropped pages, QC reports and temporary captures
outside the shipped corpus; retain required family provenance such as DLI's
manifest. After promotion, from the repository root:

```bash
poetry run corpus-crawler --json index corpus/ --db corpus/index.db
```

**Rebuilding the index reads local files only: it does not fetch policies or make
the snapshot current.** Review public corpus changes and the rebuilt database
together before publication, and update the documented counts/cutoffs.

### Maintainer-only sanitized index export

**Before publishing any rebuilt index, including after a DLI refresh**, export a
sanitized copy. The index builder records an absolute `meta.corpus_root`; changing
that value in place can leave the old path in unused SQLite pages. The ordinary
publication checker skips binary contents, so it cannot audit the database.

Close database users/writers first. From the repository root, run the following
after rebuilding. It backs up to temporary files on the same filesystem, changes
only location metadata, compacts into a fresh database and replaces the original
atomically **only after integrity and raw-byte checks pass**:

```bash
poetry run python - <<'PY'
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from scripts.check_publish_safe import scan_text

db = Path("corpus/index.db")
if any(Path(str(db) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
    raise SystemExit("Close database users and resolve SQLite sidecars before export.")

with TemporaryDirectory(prefix=".index-publish-", dir=db.parent) as temp:
    working = Path(temp) / "working.db"
    compact = Path(temp) / "publish.db"
    source_uri = db.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source:
        with closing(sqlite3.connect(working)) as copy:
            source.backup(copy)
            changed = copy.execute(
                "UPDATE meta SET value = ? WHERE key = ?", (".", "corpus_root")
            ).rowcount
            if changed != 1:
                raise SystemExit("Unexpected corpus metadata; index not replaced.")
            copy.commit()
            copy.execute("VACUUM INTO ?", (str(compact),))

    with closing(sqlite3.connect(compact)) as checked:
        if checked.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise SystemExit("SQLite integrity check failed; index not replaced.")
        root = checked.execute(
            "SELECT value FROM meta WHERE key = ?", ("corpus_root",)
        ).fetchone()
        if root != (".",):
            raise SystemExit("Unexpected corpus metadata; index not replaced.")

    # Bypass decode_for_scan's binary skip and break NUL-delimited fields,
    # so a URL cannot absorb an adjacent field containing a local path.
    audit_text = compact.read_bytes().replace(b"\x00", b"\n").decode(
        "utf-8", errors="replace"
    )
    violations = scan_text("corpus/index.db", audit_text)
    counts = dict(sorted(Counter(item.category for item in violations).items()))
    print(json.dumps({"violations": len(violations), "categories": counts}))
    if violations:
        raise SystemExit("Binary audit failed; index not replaced.")
    os.replace(compact, db)
PY
poetry run python scripts/check_publish_safe.py
```

`VACUUM INTO` discards unused pages instead of merely hiding old metadata. The
binary audit retains the existing machine-path and credential checks and reports
only violation counts/categories, never matching snippets. A failure leaves the
original rebuilt index unchanged: do not publish it; fix the source/problem and
repeat the export. These pattern checks are **not a full content or PII audit**;
publication still requires deliberately audited public sources and a review of
the corpus/index changes. No scanner exemptions or source-text edits are a
substitute for that review.

### DLI-only refresh

`refresh-dli` fetches the fixed [IRCC DLI JSON endpoint](https://www.canada.ca/content/dam/ircc/documents/json/dli/dli-full-list.json),
validates its schema and regenerates only `corpus/dli/` plus its manifest. It does
not refresh IRCC policy, NOC or legislation, or rebuild the index. It has no
`--out` option, so run the installed command from a separate staging directory
to avoid replacing the shipped family before review:

```bash
# Start from the repository root, with the package installed in the Poetry env
dli_stage="$(mktemp -d)"
crawler_python="$(poetry env info --executable)"
(cd "$dli_stage" && "$crawler_python" -m crawler.cli --json refresh-dli)
```

Review `$dli_stage/corpus/dli/`, its counts, hashes, `as_of` and live-source
coverage. Promote the **whole approved DLI family including `manifest.json`**,
so removed institutions do not linger, then run the same rebuild, sanitized
export/binary audit and publication checks above. This generator is stdlib-only;
it does not need the `crawl` extra.
Source-specific reproduction terms and required attribution are in [NOTICE](NOTICE).

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

To check tracked text and filenames for private vault artifacts, machine-specific paths or secret tokens, run the stdlib publish-safety checker:

```bash
.venv/bin/python scripts/check_publish_safe.py
```

Public source URL path segments are not treated as machine paths. Embedded local
paths, credentials and URL query values remain scanned; a source URL is not a
blanket exemption from publication-safety checks.
The checker skips binary file contents; publish a rebuilt SQLite index only
after the [maintainer export and binary audit](#maintainer-only-sanitized-index-export)
above. Neither pattern scan replaces public-source curation or a content/PII review.

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
Audited, attributed public-source corpus updates may be included with their rebuilt
index and documented cutoffs. Never include applicant documents, candidate vaults,
credentials, private corpora or unaudited local crawl outputs in a pull request.

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

* **Software License**: Code is distributed under the [MIT License](LICENSE); bundled source materials and their indexed text retain their source-specific reproduction terms, not MIT.
* **Attribution**: See [NOTICE](NOTICE) for third-party citations and corpus source attribution.
* **Disclaimer**: This system provides **substantiation screening**, NOT legal advice. It does not decide cases or guarantee IRCC application outcomes. Always consult a licensed Regulated Canadian Immigration Consultant (RCIC) or immigration lawyer for legal counsel.
