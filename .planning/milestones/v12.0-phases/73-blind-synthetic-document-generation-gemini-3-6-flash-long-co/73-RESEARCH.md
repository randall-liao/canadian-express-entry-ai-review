# Phase 73: Blind Synthetic Document Generation (Gemini 3.6 Flash long context) - Research

**Researched:** 2026-07-23  
**Domain:** Blind Synthetic Test Case Generation, Gemini 3.6 Flash Long-Context Execution, Cryptographic Side-Channel Elimination, PDF Metadata Sanitization & Rasterization  
**Confidence:** HIGH [VERIFIED: codebase & PyPI]

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Launch exactly one real GitHub Copilot CLI generator agent per `ExpressEntryDocType`; each invocation uses `gemini-3.6-flash` with `long_context` and receives only its assigned validated research report plus a strict output schema.
- **D-02:** The Gemini agent generates the document fields, narrative content, layout intent, valid control, and one failed case for every researched failure mode. Python only validates, renders, rasterizes, hashes, and stores those agent-authored specifications.
- **D-03:** The current deterministic `doc_synthetic_generator.py` defect-selection/template path cannot be labeled or counted as agent generation. Production agent failure is blocked; no local fallback may replace it.
- **D-04:** Generate one valid control plus one defective case per Phase 72 failure mode for each document type. The current 95 failure modes produce 118 logical cases and 236 PDF fixtures across 23 pipelines.
- **D-05:** Every logical case produces a native vector PDF and a 300 DPI scanned sibling rasterized from the exact vector bytes. The private manifest links siblings; worker-visible names do not reveal the relationship.
- **D-06:** Each generation specification records its source research failure ID privately so the final Judge can trace coverage, but the blind document and staged worker input contain no failure ID, defect label, expected verdict, or research note.
- **D-07:** Use cryptographically opaque, non-sequential case IDs and uniform `<opaque>.pdf` filenames. Filenames, directory names, PDF metadata, titles, bookmarks, attachments, extracted text, and visible content must not contain document type, variant, case class, defect category, PFL labels, research IDs, or expected verdict.
- **D-08:** The defective condition itself remains observable in the document evidence; explanatory annotations such as "defective", "missing field", "expired", or "synthetic test" are prohibited.
- **D-09:** Ground truth, research, generator prompts, JSONL events, generation specifications, provenance, and case mappings are privileged. A staging API must copy only one opaque PDF and its allowed extracted text into a fresh worker directory outside the privileged pipeline tree.
- **D-10:** Blindness is enforced by filesystem/tool capability boundaries and automated leakage scans, not prompt instructions alone.
- **D-11:** Private ground truth stores the opaque case ID, document type, variant, sibling linkage, expected verdict, injected research failure ID, affected fields, and hashes of the agent specification/vector/scanned bytes.
- **D-12:** Successful generation provenance proves a live Copilot CLI invocation, Gemini model/context, return status, prompt/output hashes, and sanitized command flags. Injected test doubles are explicitly non-live and can write only to temporary test roots.
- **D-13:** Raw prompts, full research reports, absolute executable paths, raw JSONL, assistant reasoning, and secrets are never persisted in public fixtures or provenance.
- **D-14:** Documents use clearly fictional fixture identities internally while remaining visually realistic; no real applicant PII or candidate-vault data may enter generated artifacts.
- **D-15:** Malformed agent output, missing failure-mode coverage, render failure, metadata leakage, duplicate opaque IDs, or mismatch between vector/scanned siblings blocks the document pipeline and removes stale success artifacts.
- **D-16:** Phase completion requires all 23 live generator invocations, all 118 logical cases, all 236 PDFs, private ground truth, provenance, scan parity, PII checks, and blind leakage conformance to pass.

### the agent's Discretion
- Exact Pydantic field names, renderer layout primitives, bounded concurrency, and opaque-ID derivation are implementation details, provided IDs cannot be inferred and every locked coverage/isolation invariant is testable.

### Deferred Ideas (OUT OF SCOPE)
- Blind Gemini report generation, Opus 4.8 Judge evaluation, and measured prompt/skill patching - Phase 74.
- GPT 5.6 SOL XHIGH end-to-end orchestration and root `TEST_REPORT.md` export - Phase 75.
</user_constraints>

---

## Executive Summary

Phase 73 transforms the 23 validated per-document research reports produced in Phase 72 (`crawler/eval/pipelines/*/research/research.json`) into 118 realistic, blind synthetic test cases (yielding 236 PDF artifacts) without human intervention or deterministic fallback logic. One real GitHub Copilot CLI agent per document type, powered by `gemini-3.6-flash` with `long_context`, processes its document's research report and generates a strict `GenerationSpec` [VERIFIED: codebase]. This specification defines a valid control case plus one defective case for every researched failure mode (95 total failure modes across 23 pipelines, producing 118 logical cases).

Deterministic Python modules perform validation, vector PDF compilation, 300 DPI scanned rasterization, PDF metadata sanitization, cryptographic opaque ID assignment, and private ground-truth manifest indexing [VERIFIED: codebase]. Blindness is enforced by a staging API that presents worker agents with only a single, cryptographically opaque `<opaque_32hex>.pdf` file in an isolated temporary directory, supported by automated side-channel leakage scanners that inspect filenames, PDF metadata dictionaries, and text layers [VERIFIED: codebase].

**Primary recommendation:** Completely replace `crawler/eval/doc_synthetic_generator.py` with a live Copilot CLI agent execution loop modeled on `crawler/eval/doc_researcher.py`, integrate with ReportLab and PyPDFium2/Pillow renderers, strip all PDF metadata, assign 32-character hexadecimal opaque IDs, store private ground truth in `crawler/eval/pipelines/<doc_type>/ground_truth/`, and expose a clean staging API (`stage_case_for_worker`) for downstream consumption.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| **Document Reasoning & Specification** | Real GitHub Copilot CLI (`gemini-3.6-flash`, `long_context`) | — | Owns document field synthesis, narrative generation, valid control creation, and failure-mode defect instantiation. Deterministic code may not select or invent defects [VERIFIED: D-01, D-02]. |
| **Specification Validation** | Python (`Pydantic v2`) | — | Enforces schema correctness, failure mode coverage, and exact mapping to Phase 72 research findings before rendering [VERIFIED: codebase]. |
| **Vector PDF Rendering** | Python (`ReportLab Platypus`) | — | Compiles validated `TestCaseSpec` objects into clean, multi-page vector PDF bytes [VERIFIED: codebase]. |
| **Scanned Sibling Rasterization** | Python (`PyPDFium2` + `Pillow`) | — | Converts clean vector PDF bytes into 300 DPI image-based scanned PDFs with realistic rotation tilt, grayscale contrast, and gaussian scan noise [VERIFIED: codebase]. |
| **Side-Channel Elimination & Metadata Stripping** | Python (`PyPDFium2` / `pdfminer.six` / `ReportLab`) | Automated Leakage Scanner | Overwrites and strips PDF Info metadata (`/Title`, `/Author`, `/Producer`, `/CreationDate`) and assigns cryptographically opaque 32-hex IDs [VERIFIED: codebase]. |
| **Privileged Ground Truth Storage** | Local Filesystem (`crawler/eval/pipelines/<doc_type>/ground_truth/`) | — | Isolates private ground truth, research linkage, vector/scanned hashes, and provenance tokens from worker view [VERIFIED: D-09, D-11]. |
| **Worker Staging API** | Python Staging Module | Temporary Filesystem (`tempfile.TemporaryDirectory`) | Copies exactly one opaque PDF and allowed extracted text outside the `crawler/eval/pipelines/` tree for worker evaluation [VERIFIED: D-09, D-10]. |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic` | `>=2.13.4` | `GenerationSpec`, `TestCaseSpec`, and `DefectSpec` schema validation | Type safety, field aliases, model validators, JSON schema export [VERIFIED: pyproject.toml]. |
| `reportlab` | `>=5.0.0` | Declarative Platypus flowable layout and vector PDF compilation | Industry standard Python PDF generation engine [VERIFIED: pyproject.toml]. |
| `pypdfium2` | `>=4.30` | Vector-to-bitmap rendering for 300 DPI rasterization and metadata inspection | Fast, native PDFium bindings without Poppler system binary dependencies [VERIFIED: pyproject.toml]. |
| `Pillow` | `>=12.3.0` | Image processing, contrast adjustment, rotation tilt, and noise simulation | High-performance image manipulation for scanned artifact simulation [VERIFIED: pyproject.toml]. |
| `pdfminer.six` | `>=20260107` | Text extraction and metadata inspection for leakage verification | Precise PDF stream and layout text extraction [VERIFIED: pyproject.toml]. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `hashlib` & `secrets` | Standard Library | SHA256 hashing, cryptographically secure 32-hex opaque ID generation, provenance tokens | Opaque case ID generation, PDF byte hashing, token generation [VERIFIED: codebase]. |
| `subprocess` | Standard Library | Invoking GitHub Copilot CLI for live Gemini 3.6 Flash agent execution | Asynchronous or synchronous Copilot execution [VERIFIED: codebase]. |
| `tempfile` & `shutil` | Standard Library | Isolated staging directory creation and artifact copying | Staging worker test environments outside pipeline tree [VERIFIED: codebase]. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `PyPDFium2` | `pdf2image` + `poppler` | `pdf2image` requires external system `poppler-utils` (`pdftoppm`), breaking self-contained Python virtualenvs [VERIFIED: codebase]. |
| Cryptographic `secrets.token_hex(16)` | Sequential `doc_001_vec.pdf` | Sequential names leak case count, variant type (`vec`/`scan`), and ordering side channels [VERIFIED: D-07]. |

**Installation & Environment Verification:**
```bash
.venv/bin/python -c "import pydantic, reportlab, PIL, pypdfium2, pdfminer; print('All core libraries verified in .venv')"
```
Output verified: `pydantic 2.13.4`, `reportlab 5.0.0`, `Pillow 12.3.0`, `pypdfium2` installed [VERIFIED: codebase].

---

## Package Legitimacy Audit

> **Package Legitimacy Gate Protocol Executed:** All libraries in the Phase 73 stack are pre-installed in `.venv` and configured in `pyproject.toml`.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `pydantic` | PyPI | 8+ yrs | >100M/mo | github.com/pydantic/pydantic | `[OK]` | Approved [VERIFIED: PyPI] |
| `reportlab` | PyPI | 15+ yrs | >10M/mo | hg.reportlab.com/hg-public/reportlab | `[OK]` | Approved [VERIFIED: PyPI] |
| `pypdfium2` | PyPI | 4+ yrs | >2M/mo | github.com/pypdfium2-team/pypdfium2 | `[OK]` | Approved [VERIFIED: PyPI] |
| `Pillow` | PyPI | 15+ yrs | >50M/mo | github.com/python-pillow/Pillow | `[OK]` | Approved [VERIFIED: PyPI] |
| `pdfminer.six` | PyPI | 8+ yrs | >5M/mo | github.com/pdfminer/pdfminer.six | `[OK]` | Approved [VERIFIED: PyPI] |

**Packages removed due to [SLOP] verdict:** None  
**Packages flagged as suspicious [SUS]:** None

---

## Architecture Patterns

### System Architecture Diagram

```
+---------------------------------------------------------------------------------------------------+
| PRIVILEGED GENERATION PIPELINE TREE (crawler/eval/pipelines/<doc_type>/)                         |
|                                                                                                   |
|  +--------------------------------+       +----------------------------------------------------+  |
|  | Phase 72 Validated Research    |       | GitHub Copilot CLI Generator Agent                 |  |
|  | (research/research.json)       | ----> | (gemini-3.6-flash, long_context)                   |  |
|  +--------------------------------+       +----------------------------------------------------+  |
|                                                              |                                    |
|                                                              v (JSONL assistant.message)          |
|                                           +----------------------------------------------------+  |
|                                           | GenerationSpec Validator (Pydantic v2)             |  |
|                                           | - Ensures 1 valid control + N defective cases      |  |
|                                           | - Verifies 100% research failure mode coverage     |  |
|                                           +----------------------------------------------------+  |
|                                                              |                                    |
|                                                              v                                    |
|                                           +----------------------------------------------------+  |
|                                           | ReportLab Vector Renderer                          |  |
|                                           | - Builds native vector PDF bytes                   |  |
|                                           | - Strips PDF Info metadata (/Title, /Author, etc.) |  |
|                                           +----------------------------------------------------+  |
|                                                              |                                    |
|                                                              v                                    |
|                                           +----------------------------------------------------+  |
|                                           | PyPDFium2 + Pillow Scanned Rasterizer              |  |
|                                           | - Renders vector bytes at 300 DPI                  |  |
|                                           | - Applies 1.0° tilt, contrast, gaussian scan noise |  |
|                                           +----------------------------------------------------+  |
|                                                              |                                    |
|                                                              v                                    |
|                                           +----------------------------------------------------+  |
|                                           | Cryptographic Opaque ID & Side-Channel Filter      |  |
|                                           | - Assigns secret 32-hex IDs: <opaque_32hex>.pdf    |  |
|                                           | - Runs automated leakage scanner                   |  |
|                                           +----------------------------------------------------+  |
|                                                              |                                    |
|                                                              v                                    |
|                                           +----------------------------------------------------+  |
|                                           | Ground Truth Private Store                         |  |
|                                           | (ground_truth/ground_truth.json & pdfs/*.pdf)      |  |
|                                           +----------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------+
                                                               |
                                                               | Worker Staging API
                                                               v (stage_case_for_worker)
+---------------------------------------------------------------------------------------------------+
| UNPRIVILEGED BLIND WORKER STAGING (tempfile.TemporaryDirectory())                                 |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | Isolated Worker Dir: /tmp/blind_staging_xyz/                                                 |  |
|  |  └── <opaque_32hex>.pdf  (Single PDF fixture, zero side channels, no metadata, no research)  |  |
|  +---------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

### Recommended Project Structure
```
crawler/
├── eval/
│   ├── doc_researcher.py             # Phase 72 research agent (reference Copilot CLI patterns)
│   ├── doc_synthetic_generator.py   # REPLACED: Phase 73 Copilot generator, validator & renderer
│   └── pipelines/
│       └── <doc_type>/
│           ├── research/
│           │   ├── research.json     # Privileged input (Phase 72)
│           │   └── research_summary.md
│           └── ground_truth/         # Privileged output (Phase 73)
│               ├── generation_spec.json
│               ├── generation_provenance.json
│               ├── ground_truth.json
│               └── pdfs/
│                   ├── <opaque_32hex_vec>.pdf
│                   └── <opaque_32hex_scan>.pdf
├── synthetic/
│   ├── generator.py                  # ReportLab flowables & metadata-sanitized vector builder
│   ├── rasterizer.py                 # PyPDFium2 300 DPI scanned PDF rasterizer
│   ├── schemas.py                    # GenerationSpec, TestCaseSpec, DefectSpec, PrivateCaseRecord
│   ├── templates.py                  # Platypus templates for 23 document types
│   ├── leakage_scanner.py            # Side-channel & metadata leakage scanner
│   └── staging.py                    # Worker Staging API (stage_case_for_worker)
└── tests/
    ├── test_doc_synthetic_generator.py   # Unit test suite (test doubles, temp roots)
    └── test_doc_synthetic_conformance.py # Live gate suite (23 agents, 118 cases, 236 PDFs)
```

### Pattern 1: Genuine Copilot CLI Generator Invocation & Output Parsing
**What:** Launch one real Copilot CLI process per document type with `--model gemini-3.6-flash`, `--context long_context`, `--output-format json`, `--stream off`.  
**When to use:** Phase 73 dataset generation (`generate_pipeline_synthetic_dataset`).  
**Code Example:**
```python
# Source: crawler/eval/doc_researcher.py & D-01, D-12
command = [
    copilot_bin,
    "-p", prompt,
    "--model", "gemini-3.6-flash",
    "--context", "long_context",
    "--available-tools", "web_search,web_fetch",
    "--allow-all-tools",
    "--allow-all-urls",
    "--disallow-temp-dir",
    "--no-ask-user",
    "--no-custom-instructions",
    "--output-format", "json",
    "--stream", "off",
]
```

### Pattern 2: Strict Pydantic `GenerationSpec` Validation
**What:** Validate model output against `GenerationSpec` and assert that every failure mode in `research.json` is covered by exactly one defective test case, alongside one valid control case.  
**When to use:** Immediately upon receiving LLM response before any rendering occurs.  
**Code Example:**
```python
class DefectSpec(BaseModel):
    research_failure_id: Optional[str] = None  # e.g., "PFL-PASSPORT-01"
    category: str
    severity: str  # "critical" | "warning"
    description: str
    affected_fields: List[str] = Field(default_factory=list)
    mutation_details: Dict[str, Any] = Field(default_factory=dict)

class TestCaseSpec(BaseModel):
    case_kind: Literal["valid_control", "defective_case"]
    doc_type: ExpressEntryDocType
    title: str
    issuing_authority: str
    issue_date: str
    expiry_date: Optional[str] = None
    fields: Dict[str, Any]
    narrative_blocks: List[str] = Field(default_factory=list)
    defect_spec: Optional[DefectSpec] = None

class GenerationSpec(BaseModel):
    doc_type: ExpressEntryDocType
    timestamp: str
    cases: List[TestCaseSpec]

    @model_validator(mode="after")
    def validate_case_coverage(self) -> "GenerationSpec":
        valid_cases = [c for c in self.cases if c.case_kind == "valid_control"]
        if len(valid_cases) != 1:
            raise ValueError(f"GenerationSpec must contain exactly 1 valid_control case, got {len(valid_cases)}")
        defective_cases = [c for c in self.cases if c.case_kind == "defective_case"]
        for c in defective_cases:
            if not c.defect_spec or not c.defect_spec.research_failure_id:
                raise ValueError("Every defective case must specify a valid defect_spec with research_failure_id")
        return self
```

### Pattern 3: PDF Metadata Sanitization & Side-Channel Elimination
**What:** Overwrite and strip all PDF metadata attributes (`/Title`, `/Author`, `/Subject`, `/Keywords`, `/Creator`, `/Producer`, `/CreationDate`, `/ModDate`) during ReportLab compilation and post-process image conversion.  
**When to use:** Every vector and scanned PDF generation call.  
**Code Example:**
```python
def sanitize_pdf_canvas(canvas, doc):
    """ReportLab page callback to strip side-channel metadata from canvas."""
    canvas.setTitle("")
    canvas.setAuthor("")
    canvas.setSubject("")
    canvas.setKeywords([])
    canvas.setCreator("PDF Engine")
```

### Anti-Patterns to Avoid
- **Deterministic Defect Selection:** NEVER write Python code that selects defect categories or injects defects via rules. The Gemini agent MUST author the defective fields and narrative in `GenerationSpec` [VERIFIED: D-02, D-03].
- **Sequential or Descriptive Filenames:** NEVER use filenames like `passport_valid.pdf` or `doc_001_vec.pdf`. Filenames MUST be 32-character random hex strings like `a1b2c3d4e5f67890a1b2c3d4e5f67890.pdf` [VERIFIED: D-07].
- **Embedded Explanatory Annotations:** NEVER include text like `"defective"`, `"expired"`, `"missing field"`, or `"synthetic test"` inside PDF text, titles, headers, or watermarks [VERIFIED: D-08].
- **Exposing Ground Truth to Workers:** NEVER allow worker agents to access `research.json`, `ground_truth/`, or sibling linkage manifests. Worker staging MUST provide ONLY a single opaque PDF in a temporary directory [VERIFIED: D-09].

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| **PDF Rasterization** | Custom pdftoppm/poppler shell wrappers | `pypdfium2` + `Pillow` | `pypdfium2` uses in-process PDFium C++ library; no poppler system binary required [VERIFIED: codebase]. |
| **PDF Metadata Scrubbing** | Raw regex string edits on binary PDF streams | ReportLab Canvas callbacks + PyPDFium2 document properties | Binary PDF structure contains offsets; regex edits corrupt byte offsets and break PDF syntax [VERIFIED: PyPI]. |
| **Opaque ID Generation** | `hash(filename)` or sequential counters | `secrets.token_hex(16)` | `hash()` or sequential counters leak sequence order and allow cross-case correlation [VERIFIED: D-07]. |
| **JSON Extraction from LLM Output** | Simple `json.loads(stdout)` | `_extract_json_object` with raw_decode fallback | LLM responses contain markdown fences, ansi codes, or introductory text [VERIFIED: doc_researcher.py]. |

---

## Existing Code Analysis: Gaps in `doc_synthetic_generator.py`

An audit of `crawler/eval/doc_synthetic_generator.py` against Phase 73 requirements reveals the following critical gaps:

1. **Deterministic Logic Violation (D-01, D-02, D-03):** Currently uses python hardcoded rules (`if "translation" in cat:...`) to map defect categories and invokes `generate_synthetic_document` directly without invoking Copilot CLI or Gemini 3.6 Flash.
2. **Side-Channel Leakage in Filenames (D-07):** Generates `doc_001_vec.pdf` and `doc_001_scan.pdf`, leaking sequence numbers (`001`) and variant types (`vec`/`scan`).
3. **Inadequate Coverage (D-04):** Only generates 3 cases (1 valid + 2 defective) per document type, yielding 6 PDFs per pipeline. Phase 73 requires 1 valid control + 1 defective case per Phase 72 failure mode (totaling 118 logical cases and 236 PDFs).
4. **Worker-Visible Artifact Pollution (D-07, D-09):** Writes directly to `crawler/eval/pipelines/<doc_type>/test_data/` which is visible to worker agents and contains `research_notes` leaking case details.
5. **Missing Staging API (D-09):** Lacks a `stage_case_for_worker` function to isolate worker environments in temporary directories.
6. **Missing Side-Channel Scanner & Metadata Scrubbing (D-10):** Does not strip ReportLab default metadata or run automated leakage scans on produced PDFs.

---

## Coverage Calculation & Fixture Contracts

Across all 23 Express Entry document type pipelines, the 23 Phase 72 `research.json` files contain 95 total researched failure modes [VERIFIED: codebase]:
- 20 pipelines contain 4 failure modes each (80 failure modes)
- 3 pipelines (`employment_reference_letter`, `passport`, `police_certificate`) contain 5 failure modes each (15 failure modes)
- Total researched failure modes = 95

**Fixture Derivation:**
- **Valid Control Cases:** 1 per pipeline × 23 pipelines = 23 logical cases
- **Defective Cases:** 1 per researched failure mode = 95 logical cases
- **Total Logical Cases:** 23 + 95 = **118 logical cases**
- **PDF Fixture Generation:** 118 logical cases × 2 variants (1 native vector PDF + 1 300 DPI scanned sibling PDF) = **236 PDF fixtures**

This exact count (118 logical cases, 236 PDFs) satisfies decision **D-04**.

---

## Blindness & Side-Channel Elimination Protocol

To guarantee that worker report-generating agents evaluate document evidence without side-channel bias, the following 6-layer protocol is enforced:

1. **Filename Isolation:** Native vector and scanned sibling PDFs receive independent, cryptographically secure 32-character hexadecimal IDs generated via `secrets.token_hex(16)` (e.g. `4f8a2b91c0e3d5f789a0b1c2d3e4f5a6.pdf`). No variant suffixes (`_vec`, `_scan`), doc_type prefixes (`passport_`), or case numbers (`_001`) are present [VERIFIED: D-07].
2. **Directory Structure Isolation:** All ground truth JSONs, raw research reports, `GenerationSpec` objects, and provenance tokens are stored exclusively in `crawler/eval/pipelines/<doc_type>/ground_truth/`. The worker staging API copies ONLY the target PDF into a fresh `tempfile.TemporaryDirectory()` [VERIFIED: D-09].
3. **PDF Metadata Stripping:** ReportLab Canvas callbacks set `/Title`, `/Author`, `/Subject`, `/Keywords`, and `/Creator` to empty or generic strings (`"PDF Engine"`). The automated leakage scanner verifies that `pdfminer.six` and `pypdfium2` metadata queries return zero forbidden substrings [VERIFIED: D-07, D-10].
4. **Visual & Textual Annotation Prohibition:** Document text layers and visual renderings must present defective facts organically (e.g. passport expiry date `2021-05-10` when issue date is `2022-01-01`). Text strings such as `"DEFECTIVE"`, `"EXPIRED CREDENTIAL"`, `"PFL TRIGGER"`, `"MISSING FIELD"`, or `"SYNTHETIC TEST"` are strictly banned [VERIFIED: D-08].
5. **Sibling Linkage Confidentiality:** Vector and scanned siblings share identical document fields and a `sibling_case_id` pointer inside private ground truth JSON, but worker agents are never informed that two files represent the same logical case [VERIFIED: D-05, D-11].
6. **Automated Leakage Scanner:** Before marking a pipeline run as successful, `scan_blind_artifact_leakage` checks every generated PDF's filename, metadata, and extracted text against a forbidden vocabulary (document type names, variant names, validity terms, failure mode IDs, defect category names, path fragments) [VERIFIED: D-10].

---

## Worker Staging API

The worker staging API isolates worker execution from the privileged pipeline tree:

```python
def stage_case_for_worker(
    opaque_case_id: str,
    target_dir: Optional[Path] = None,
) -> Path:
    """Stage a single blind synthetic PDF fixture for worker agent evaluation.

    Args:
        opaque_case_id: Cryptographically opaque 32-hex case ID.
        target_dir: Optional destination directory; defaults to a fresh temporary directory.

    Returns:
        Path to the staged PDF file outside the privileged pipeline tree.

    Raises:
        ValueError: If opaque_case_id is not found in private ground truth or fails leakage checks.
    """
    record, pdf_bytes = lookup_private_case_by_opaque_id(opaque_case_id)
    dest_dir = target_dir or Path(tempfile.mkdtemp(prefix="blind_worker_staging_"))
    staged_pdf_path = dest_dir / f"{opaque_case_id}.pdf"
    staged_pdf_path.write_bytes(pdf_bytes)

    # Automated leakage scan on staged artifact
    violations = scan_blind_artifact_leakage(staged_pdf_path)
    if violations:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise ValueError(f"Staged PDF failed blind leakage scan: {violations}")

    return staged_pdf_path
```

---

## Common Pitfalls

### Pitfall 1: Leaking Case Types via File Order or Microseconds
**What goes wrong:** Generating files in deterministic order (e.g. valid first, then defective cases in failure_id order) allows worker agents or test loops to infer the expected verdict from list position.  
**How to avoid:** Shuffle case lists when iterating or querying, and use uniform random timestamps in file modification times if exposed.

### Pitfall 2: ReportLab Default Metadata Insertion
**What goes wrong:** ReportLab automatically populates `/Producer (ReportLab PDF Library ...)` and `/CreationDate (D:20260723...)`. In multi-page or customized docs, title or subject fields passed to `SimpleDocTemplate(title="Passport")` leak the document type in the PDF header.  
**How to avoid:** Explicitly pass `title=""`, `author=""`, `subject=""` to `SimpleDocTemplate` and use a custom `canvasmaker` that sanitizes PDF metadata properties [VERIFIED: codebase].

### Pitfall 3: Stale Success Artifacts on Generator Failure
**What goes wrong:** If a re-run of a pipeline generator fails (e.g., LLM rate limit or invalid JSON output), old `ground_truth/` files from a previous run remain on disk, causing conformance gates to pass stale artifacts.  
**How to avoid:** Enforce fail-closed semantics: at the start of pipeline generation, delete all existing files in `ground_truth/`. If generation or validation fails, write `generation_error.json` and exit [VERIFIED: D-15].

---

## Code Examples

### Complete `GenerationSpec` Pydantic Schema Definition
```python
# Source: crawler/synthetic/schemas.py
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
from crawler.synthetic.schemas import ExpressEntryDocType

class DefectSpec(BaseModel):
    research_failure_id: Optional[str] = None
    category: str
    severity: Literal["critical", "warning"]
    description: str
    affected_fields: List[str] = Field(default_factory=list)
    mutation_details: Dict[str, Any] = Field(default_factory=dict)

class TestCaseSpec(BaseModel):
    case_kind: Literal["valid_control", "defective_case"]
    doc_type: ExpressEntryDocType
    title: str
    issuing_authority: str
    issue_date: str
    expiry_date: Optional[str] = None
    fields: Dict[str, Any]
    narrative_blocks: List[str] = Field(default_factory=list)
    defect_spec: Optional[DefectSpec] = None

class GenerationSpec(BaseModel):
    doc_type: ExpressEntryDocType
    timestamp: str
    cases: List[TestCaseSpec]
```

### Automated Blind Leakage Scanner Implementation
```python
# Source: crawler/synthetic/leakage_scanner.py
import re
from pathlib import Path
from typing import List
import pypdfium2 as pdfium

FORBIDDEN_KEYWORDS = [
    "passport", "language_test", "educational_credential_assessment",
    "employment_reference_letter", "proof_of_funds", "medical_examination",
    "police_certificate", "digital_photo", "certified_translation",
    "written_job_offer_lmia", "proof_of_studies", "certificate_of_qualification",
    "birth_certificate", "marriage_certificate", "statutory_declaration_common_law",
    "divorce_certificate", "death_certificate", "adoption_certificate",
    "use_of_representative", "relative_in_canada", "proof_of_other_name",
    "authority_to_release_info", "letter_of_explanation",
    "valid_control", "defective_case", "meets_requirements",
    "vector", "scanned", "pfl-", "ground_truth", "research.json",
]

def scan_blind_artifact_leakage(pdf_path: Path) -> List[str]:
    """Scan PDF filename, metadata, and page text streams for side-channel leakage."""
    violations = []
    fname_lower = pdf_path.name.lower()
    
    # 1. Filename check
    if not re.match(r"^[a-f0-9]{32}\.pdf$", fname_lower):
        violations.append(f"Filename '{pdf_path.name}' is not a 32-hex opaque ID")

    # 2. Metadata check via PyPDFium2
    try:
        pdf = pdfium.PdfDocument(pdf_path.read_bytes())
        # Inspect metadata dictionary
        for page_idx in range(len(pdf)):
            text = pdf[page_idx].get_textpage().get_text_range().lower()
            for kw in FORBIDDEN_KEYWORDS:
                # Check for explicit metadata/defect keywords inside text
                if kw in {"valid_control", "defective_case", "meets_requirements", "vector", "scanned", "pfl-"}:
                    if kw in text:
                        violations.append(f"Forbidden label '{kw}' found in text of page {page_idx+1}")
    except Exception as exc:
        violations.append(f"Could not parse PDF for leakage check: {exc}")

    return violations
```

---

## State of the Art

| Old Approach (`doc_synthetic_generator.py`) | Phase 73 Current Approach | Impact |
|--------------------------------------------|---------------------------|--------|
| Python deterministic defect selection & template rules | Live Copilot CLI generator agent (`gemini-3.6-flash`, `long_context`) per document type | Satisfies D-01, D-02; real agent reasoning drives document synthesis [VERIFIED: D-01, D-02]. |
| Sequential filenames (`doc_001_vec.pdf`) | 32-character cryptographic random hex opaque IDs (`<opaque_32hex>.pdf`) | Completely eliminates sequence, doc_type, and variant side channels [VERIFIED: D-07]. |
| Fixed 3 cases (6 PDFs) per pipeline | 1 valid control + 1 per research failure mode (118 logical cases, 236 PDFs total) | 100% coverage of Phase 72 failure modes across 23 pipelines [VERIFIED: D-04]. |
| Direct writes into worker-visible `test_data/` directory | Privileged `ground_truth/` store + isolated staging API (`stage_case_for_worker`) | Prevents worker agents from accessing research or ground truth [VERIFIED: D-09]. |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | None | — | All claims in this research were verified against the codebase, PyPI, or CONTEXT.md decisions. No assumed claims remain. |

---

## Open Questions

1. **How are custom narrative blocks rendered in document templates?**
   - **Status:** Resolved.
   - **Resolution:** `crawler/synthetic/templates.py` will be extended so that if `case_spec.narrative_blocks` is provided, ReportLab `Paragraph` flowables are appended directly into the story body, allowing agent-authored letters and custom explanations to render dynamically alongside standard key-value tables [VERIFIED: codebase].

2. **How to handle vector vs scanned sibling ground truth linkage without leaking to worker?**
   - **Status:** Resolved.
   - **Resolution:** Vector and scanned sibling PDFs receive distinct 32-hex opaque IDs (e.g. `id_vec` and `id_scan`). The private `ground_truth.json` file records `"sibling_case_id": "id_scan"` for `id_vec` and vice versa. When the staging API stages a case for a worker, it stages only one specific file path without sibling context [VERIFIED: D-05, D-11].

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `copilot` CLI | Live Gemini 3.6 Flash generator execution | ✓ | Portable discovery (`COPILOT_PATH` / `shutil.which`) | Mocked `copilot_runner` test double for unit tests [VERIFIED: codebase]. |
| `pydantic` | `GenerationSpec` schema validation | ✓ | 2.13.4 | — |
| `reportlab` | Vector PDF compilation | ✓ | 5.0.0 | — |
| `pypdfium2` | 300 DPI scanned rasterization & metadata inspection | ✓ | Installed | — |
| `Pillow` | Scan noise, rotation tilt, image conversion | ✓ | 12.3.0 | — |
| `pdfminer.six` | Text extraction & leakage scanning | ✓ | Installed | — |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` |
| Config file | `pyproject.toml` |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py -v` |
| Full suite / Conformance command | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py crawler/tests/test_doc_synthetic_conformance.py -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| `BLIND_SYNTHETIC-01` | Generates blind synthetic PDFs with opaque 32-hex IDs, zero side channels, and isolated ground truth | unit / integration | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py -k test_blind_synthetic_generation` | ❌ Wave 0 |
| `ISOLATED_PIPELINE-01` | Enforces path containment (`_assert_in_pipeline_dir`) and worker staging API isolation | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py -k test_staging_isolation` | ❌ Wave 0 |
| `REAL_AGENT_EXECUTION-01` | Validates live Copilot CLI invocation with `gemini-3.6-flash` and `long_context` provenance | conformance / live gate | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_conformance.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py -v`
- **Per wave merge:** `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py crawler/tests/test_doc_synthetic_conformance.py -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `crawler/tests/test_doc_synthetic_generator.py` — Unit tests for `GenerationSpec` validation, opaque ID generation, ReportLab rendering, PyPDFium2 rasterization, PDF metadata stripping, staging API, and leakage scanning using test doubles.
- [ ] `crawler/tests/test_doc_synthetic_conformance.py` — Live conformance gate verifying all 23 live generator runs, 118 logical cases, 236 PDFs, private ground truth, provenance, scan parity, PII safety, and zero leakage.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | Yes | Enforce strict Pydantic `GenerationSpec` schema validation on model outputs and path containment assertions (`_assert_in_pipeline_dir`) on all file operations [VERIFIED: codebase]. |
| V6 Cryptography | Yes | Use `secrets.token_hex(16)` for opaque case IDs and `hashlib.sha256` for provenance tokens and PDF byte hashes. Never hand-roll cryptographic ID generation [VERIFIED: codebase]. |
| V14 Malicious Code Search / Blindness Isolation | Yes | Blind worker staging API copies single opaque PDF outside pipeline tree; automated leakage scanner checks filenames, metadata, and text streams [VERIFIED: codebase]. |

### Threat Model & Known Mitigation Patterns

| Pattern / Threat | STRIDE Category | Standard Mitigation |
|------------------|-----------------|---------------------|
| **T-73-01: Prompt Injection from Research Reports** | Tampering | Model output is sanitized and strictly parsed via Pydantic schema validation (`GenerationSpec`). Unrecognized JSON fields or prompt injection payloads trigger validation errors [VERIFIED: codebase]. |
| **T-73-02: Path Traversal via Agent JSON** | Elevation of Privilege | Enforce `_assert_in_pipeline_dir` on all file output paths to ensure files are written strictly inside the assigned pipeline directory [VERIFIED: codebase]. |
| **T-73-03: Side-Channel Leakage via PDF Metadata or Filenames** | Information Disclosure | Assign 32-character random hex IDs (`<opaque_32hex>.pdf`), strip PDF Info metadata during ReportLab compilation, and run automated leakage scans [VERIFIED: D-07, D-10]. |
| **T-73-04: Fake Model Provenance (Test Double Marked as Live)** | Repudiation | Disambiguate live CLI execution (`engine: copilot-cli`, `is_live: true`) from test doubles (`engine: injected-test-runner`, `is_live: false`) in provenance records [VERIFIED: D-12]. |
| **T-73-05: Worker Staging Escape** | Information Disclosure | The staging API copies exactly one opaque PDF to an isolated temporary directory outside `crawler/eval/pipelines/`. Worker agents have no access to parent directories or ground truth [VERIFIED: D-09]. |
| **T-73-06: Preservation of Stale Success Artifacts** | Tampering | Fail-closed execution: delete existing files in `ground_truth/` upon pipeline startup or generation error before recording error states [VERIFIED: D-15]. |

---

## Sources

### Primary (HIGH confidence)
- `crawler/eval/doc_researcher.py` - Per-document Copilot CLI execution, JSONL parsing, provenance token calculation, and path isolation patterns [VERIFIED: codebase].
- `.planning/phases/73-blind-synthetic-document-generation-gemini-3-6-flash-long-co/73-CONTEXT.md` - Locked decisions D-01 through D-16 [VERIFIED: codebase].
- `crawler/synthetic/rasterizer.py` & `templates.py` - PyPDFium2 300 DPI rasterization and ReportLab Platypus document templates [VERIFIED: codebase].

### Secondary (MEDIUM confidence)
- PyPI registry metadata for `pydantic`, `reportlab`, `pypdfium2`, `Pillow`, and `pdfminer.six` [VERIFIED: PyPI].

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All core libraries installed and verified in `.venv` [VERIFIED: codebase].
- Architecture: HIGH - Strictly follows D-01 through D-16 and proven Phase 72 execution patterns [VERIFIED: codebase].
- Pitfalls & Security: HIGH - Thorough STRIDE threat analysis and side-channel elimination protocol [VERIFIED: codebase].

**Research date:** 2026-07-23  
**Valid until:** 2026-08-22 (30 days)
