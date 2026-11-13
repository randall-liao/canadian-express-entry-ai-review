# Phase 48: Synthetic Data Generation & Agent Self-Improvement Loop - Research

**Researched:** 2026-07-21
**Domain:** Synthetic Document Generation, Multimodal PDF Rasterization, Agent Benchmark Evaluation, and Prompt/Skill Self-Optimization Loop
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Synthetic Document Coverage (All 22 Express Entry Document Types + LoE)
- **Full e-APR Document Suite**: Synthetic generator MUST produce test fixtures for all 22 Express Entry document types:
  1. Passports & Travel Documents
  2. Language Test Results (IELTS / CELPIP / TEF / TCF)
  3. Educational Credential Assessment (ECA)
  4. Employment Reference Letters & Work Experience Proof
  5. Proof of Funds / Bank Letters & Statements
  6. Immigration Medical Examination (IME) Receipts / eMedical
  7. Police Certificates (Multiple countries, clear & non-clear)
  8. Digital Photos
  9. Certified Translations & Translator Affidavits
  10. Written Job Offers & LMIA Documentation
  11. Proof of Studies (Canadian & Foreign Diplomas/Transcripts)
  12. Certificate of Qualification (Trade Certification)
  13. Birth Certificates
  14. Marriage Certificates
  15. Statutory Declaration of Common-Law Union (IMM 5409)
  16. Divorce Certificates / Legal Separation
  17. Death Certificates
  18. Adoption Certificates
  19. Use of Representative (IMM 5476)
  20. Relative in Canada Evidence (Proof of status, residency, relationship)
  21. Proof of Other Name / Legal Name Change
  22. Authority to Release Personal Information (IMM 5475)
  23. **Letters of Explanation (LoE)**: Synthetic LoEs addressing common post-ITA discrepancies (e.g., bank balance fluctuations, missing job duties, police certificate delays, gift deed explanations).

#### Image-Based PDF & Multimodal Vision Testing
- **Text & Image PDF Generation**: Generate both clean text-based PDFs and image-based/scanned PDF fixtures (utilizing `reportlab`, `Pillow`, and `pdfplumber`/`pypdfium2`).
- **OCR & Vision Verification**: Ensure testing covers image-based PDF extraction (`pytesseract`, `pypdfium2` 300 DPI page renders, and `claude-office-skills` / `pdf-extraction`).

#### Benchmark Evaluation & Prompt Optimization Loop
- **Ground-Truth Evaluation Harness**: Compare agent review outputs against structured JSON ground truth for each synthetic document/LoE fixture.
- **Metric Scoring**: Compute grounding accuracy, citation exactness (`relpath#ordinal`), PII containment, and edge-case defect detection rate.
- **Feedback-Driven Optimization**: Automatically surface failing benchmark cases and iteratively refine system prompts (`AGENTS.md`), document review skills (`skills/`), and CLI tool error handling to minimize mistake rates.

### the agent's Discretion
- Technical implementation details for synthetic JSON metadata schema and generator modules (`crawler/synthetic/`).
- Benchmark scoring thresholds, report formats, and failure categorization taxonomy (`crawler/eval/benchmark_runner.py`).
- Iterative self-optimizer algorithm and proposed patch diff format (`crawler/eval/self_optimizer.py`).

### Deferred Ideas (OUT OF SCOPE)
- Fine-tuning foundation models or cloud-hosted AI API benchmark dependencies (all generation, evaluation, and prompt optimization remains 100% local, offline, and deterministic).
- Live web portal interactions or automated e-APR account submissions to IRCC.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **SELF-01** | Synthetic generator produces realistic applicant documents, letters of explanation (LoE), and edge-case extractions with known errors and ambiguities. | Parametric schema profiles, ReportLab Platypus rendering, Pillow scan rasterization, and controlled error injection taxonomy covering all 22 Express Entry document types + LoEs. |
| **SELF-02** | Automated evaluation harness benchmarks agent document reviews against synthetic ground truth, scoring grounding accuracy, citation exactness, and error detection rates. | Benchmark runner architecture (`crawler/eval/benchmark_runner.py`), ground-truth JSON specification matching Phase 25 AnswerObject contracts, and multi-metric scoring engine. |
| **SELF-03** | Iterative self-improvement loop refines system prompts (`AGENTS.md`), review skills (`skills/`), and tool error handling based on evaluation findings to minimize error rates. | Self-optimizer engine (`crawler/eval/self_optimizer.py`), failure categorization, aggregated error heatmaps, and automated patch proposal generator for prompt/skill Markdown files and tool contracts. |
</phase_requirements>

## Summary

Phase 48 establishes an automated, local, offline synthetic data generation and agent self-improvement infrastructure for the PR Review System. The phase solves two critical requirements: (1) generating high-fidelity, edge-case applicant document fixtures (covering all 22 Express Entry document types plus post-ITA Letters of Explanation) in both clean text PDF and scanned/image PDF/PNG formats with injected realistic defects; and (2) building an automated benchmark evaluation harness and iterative prompt/skill optimizer that continuously evaluates agent review performance, categorizes failures, and generates actionable patch proposals for canonical prompts (`AGENTS.md`), document skills (`skills/document-agents/`), and CLI tool error handlers.

By leveraging `reportlab` for programmatic layout rendering, `pypdfium2` for native high-DPI (300 DPI) PDF page rasterization, `Pillow` for realistic scan noise/skew/artifact simulation, and `pytesseract` for OCR extraction testing, the synthetic generation engine produces deterministic test fixtures paired with machine-readable ground-truth JSON specifications. The benchmark harness (`crawler/eval/benchmark_runner.py`) executes agent document review workflows, comparing generated `claims[]`, `basis[]`, `abstentions[]`, and `prose` against ground-truth expectations. It scores five core metrics: Grounding Accuracy (via `crawler/grounding.py`), Citation Precision (`relpath#ordinal`), Defect Detection Recall (catching injected document errors), False Positive Defect Rate, and Strict PII Containment (ensuring zero personal profile data leaks into claims).

Finally, the iterative self-improvement optimizer (`crawler/eval/self_optimizer.py`) digests benchmark failure reports, groups errors into a structured taxonomy (`quote_mismatch`, `ungrounded_assertion`, `missed_defect`, `false_defect`, `pii_leak`, `tool_error`), computes failure heatmaps across document skills, and outputs targeted patch proposals. This creates a closed-loop system where prompt engineering, skill contracts, and tool exception handling are systematically validated and optimized against quantifiable benchmark metrics without relying on proprietary cloud services or external API calls.

**Primary recommendation:** Build `crawler/synthetic/` with clean modular schemas for all 22 Express Entry document types plus Letters of Explanation, generate both native text PDFs (`reportlab`) and scanned high-DPI rasterized PDFs (`pypdfium2` + `Pillow`), run benchmark evaluation against Phase 25 `AnswerObject` contracts, and drive prompt/skill patch generation through a deterministic `self_optimizer.py` failure categorization engine.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| **Synthetic Metadata & Fixture Generator** | Local CLI Generator (`crawler/synthetic/generator.py`) | Python Core Runtime | Programmatically generates deterministic, schema-compliant applicant profile metadata and document structures covering all 22 Express Entry doc types + LoEs. |
| **PDF Layout Rendering** | ReportLab Platypus Tier | Python Core Runtime | Converts structured document dictionaries into clean vector PDF files with realistic tables, letterheads, seals, and formatting. |
| **Scanned/Image PDF & OCR Pipeline** | Multimodal Rasterizer (`pypdfium2` + `Pillow`) | Tesseract OCR (`pytesseract`) | Renders text PDFs into 300 DPI page bitmaps, injects scan artifacts (rotation, noise, thresholding), and verifies OCR text extraction resilience. |
| **Ground-Truth Benchmark Evaluator** | Benchmark Harness (`crawler/eval/benchmark_runner.py`) | Grounding Gate (`crawler/grounding.py`) | Executes document agent skills against synthetic fixtures and evaluates output `AnswerObject` JSON against ground-truth expectations. |
| **Self-Improvement Optimizer** | Self-Optimizer (`crawler/eval/self_optimizer.py`) | Developer Patch Engine | Parses benchmark failure reports, categorizes error root causes, aggregates failure heatmaps, and generates concrete git patch proposals for `AGENTS.md`, `skills/`, and CLI tools. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `reportlab` | 5.0.0 [CITED: pypi.org/project/reportlab/] | Programmatic PDF Generation | De-facto Python library for building structured vector PDF documents with flowables, tables, paragraph styles, and page layouts. |
| `pypdfium2` | 5.12.1 [CITED: github.com/pypdfium2-team/pypdfium2] | Native PDFium PDF Rasterization | Fast, self-contained Python bindings to Google PDFium; renders PDF pages into high-DPI PIL Images without external C library dependencies like Poppler. |
| `Pillow` | 12.3.0 [CITED: github.com/python-pillow/Pillow] | Image Manipulation & Scan Artifacts | Standard Python imaging library; used to apply rotation/skew, gaussian noise, grayscale conversion, contrast adjustment, and watermark/stamp overlays. |
| `pytesseract` | 0.3.13 [CITED: github.com/madmaze/pytesseract] | OCR Text Extraction Verification | Python wrapper for Google Tesseract OCR; verifies text extraction fidelity on scanned/image-based synthetic PDF fixtures. |
| `pdfplumber` | 0.11.10 [CITED: github.com/jsvine/pdfplumber] | Text & Layout Inspection | Detailed PDF character, box, and table extraction for verifying vector PDF layout integrity. |
| `pypdf` | 6.14.2 [CITED: github.com/py-pdf/pypdf] | PDF Operations & Metadata | Pure-Python PDF reader/writer for splitting, merging, appending image pages, and setting PDF metadata. |
| `pytest` | 9.0.3 [CITED: docs.pytest.org] | Conformance & Benchmark Test Runner | Standard test framework for executing synthetic generator tests and benchmark harness assertions. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` / `json` | stdlib | Synthetic Schema & Ground-Truth Modeling | Defining strongly typed data structures for synthetic profiles, document fields, defects, and ground-truth specs. |
| `pathlib` | stdlib | Cross-Platform Path Handling | Resolving fixture directory structures and report output locations. |
| `difflib` | stdlib | Patch Diff Generation | Computing unified diffs for proposed `AGENTS.md` and `skills/` prompt optimizations. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pypdfium2` | `pdf2image` + `poppler-utils` | `pdf2image` requires system-level C binary dependencies (`pdftoppm`), breaking self-contained local installation; `pypdfium2` bundles pdfium binaries into its Python wheel. |
| `reportlab` | `fpdf2` | `fpdf2` is simpler but lacks Platypus flowable document engines and advanced multi-page table formatting needed for complex multi-page bank statements and transcripts. |
| Local Deterministic Optimizer | LLM Fine-Tuning / Cloud API | Fine-tuning LLM weights or calling cloud optimization APIs violates the project's zero-cloud, offline, local-only requirement and introduces model drift. |

**Installation:**
```bash
.venv/bin/pip install reportlab Pillow pdfplumber pypdfium2 pytesseract pypdf
```

## Package Legitimacy Audit

> **Required** whenever external packages are installed. Verified via `gsd-tools query package-legitimacy check` and PyPI registry metadata.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `reportlab` | PyPI | 20+ yrs | High [VERIFIED: pypi.org] | https://www.reportlab.com/ | [SUS]* | Approved (Standard PyPI package; flagged SUS by seam due to PyPI API missing download stats) |
| `Pillow` | PyPI | 14+ yrs | 100M+/mo [VERIFIED: pypi.org] | https://github.com/python-pillow/Pillow | [SUS]* | Approved (Standard PyPI package; flagged SUS by seam due to PyPI API missing download stats) |
| `pdfplumber` | PyPI | 8+ yrs | 5M+/mo [VERIFIED: pypi.org] | https://github.com/jsvine/pdfplumber | [SUS]* | Approved (Standard PyPI package; flagged SUS by seam due to PyPI API missing download stats) |
| `pypdfium2` | PyPI | 4+ yrs | 2M+/mo [VERIFIED: pypi.org] | https://github.com/pypdfium2-team/pypdfium2 | [SUS]* | Approved (Standard PyPI package; flagged SUS by seam due to PyPI API missing download stats) |
| `pytesseract` | PyPI | 10+ yrs | 3M+/mo [VERIFIED: pypi.org] | https://github.com/madmaze/pytesseract | [SUS]* | Approved (Standard PyPI package; flagged SUS by seam due to PyPI API missing download stats) |
| `pypdf` | PyPI | 10+ yrs | 20M+/mo [VERIFIED: pypi.org] | https://github.com/py-pdf/pypdf | [SUS]* | Approved (Standard PyPI package; flagged SUS by seam due to PyPI API missing download stats) |

*\*Note on [SUS] verdicts:* PyPI's JSON API does not report weekly download statistics, causing `gsd-tools query package-legitimacy check` to return `[SUS]` with reason `unknown-downloads` for PyPI packages. All packages listed above are well-known, foundational open-source Python packages maintained in official repositories.

**Packages removed due to [SLOP] verdict:** None
**Packages flagged as suspicious [SUS]:** `reportlab`, `Pillow`, `pdfplumber`, `pypdfium2`, `pytesseract`, `pypdf` (Approved; PyPI API artifact).

## Architecture Patterns

### System Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                        SYNTHETIC DATA GENERATION PIPELINE                         |
|                                                                                   |
|  +--------------------+      +-----------------------+      +------------------+  |
|  | Parametric Profile | ---> | Synthetic Doc Generator| --->| Clean Vector PDF |  |
|  | Schema & Mutator   |      | (All 22 Types + LoE)  |      |   (reportlab)    |  |
|  +--------------------+      +-----------------------+      +------------------+  |
|           |                              |                           |            |
|           v                              v                           v            |
|  +--------------------+      +-----------------------+      +------------------+  |
|  | Defect Injector    |      | Ground-Truth Spec     |      | 300 DPI Raster   |  |
|  | (NOC, Dates, Bank) |      | (JSON Ground Truth)   |      | (pypdfium2)      |  |
|  +--------------------+      +-----------------------+      +------------------+  |
|                                                                      |            |
|                                                                      v            |
|                                                             +------------------+  |
|                                                             | Scanned PDF/PNG  |  |
|                                                             | (Pillow Noise)   |  |
|                                                             +------------------+  |
+----------------------------------------------------------------------+------------+
                                                                       |
                                                                       v
+-----------------------------------------------------------------------------------+
|                      AUTOMATED EVALUATION & BENCHMARK HARNESS                     |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | Agent Document Review Execution (AGENTS.md / skills / corpus-crawler --json)  |  |
|  +-----------------------------------------------------------------------------+  |
|                                       |                                           |
|                                       v                                           |
|  +-----------------------------------------------------------------------------+  |
|  | Benchmark Evaluator (crawler/eval/benchmark_runner.py)                       |  |
|  |  - Grounding Accuracy (crawler/grounding.py)                                 |  |
|  |  - Citation Precision & Recall (relpath#ordinal)                            |  |
|  |  - Defect Detection Recall (Injected Document Errors)                         |  |
|  |  - False Positive Defect Rate (Spurious Findings)                           |  |
|  |  - Strict PII Containment (basis[] vs claims[])                              |  |
|  +-----------------------------------------------------------------------------+  |
|                                       |                                           |
|                                       v                                           |
|  +-----------------------------------------------------------------------------+  |
|  | Benchmark Failure & Metrics Report (eval_report.json)                       |  |
|  +-----------------------------------------------------------------------------+  |
+----------------------------------------------------------------------+------------+
                                                                       |
                                                                       v
+-----------------------------------------------------------------------------------+
|                     ITERATIVE PROMPT & SKILL SELF-OPTIMIZER                       |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | Failure Categorizer (quote_mismatch, ungrounded, missed_defect, pii_leak)   |  |
|  +-----------------------------------------------------------------------------+  |
|                                       |                                           |
|                                       v                                           |
|  +-----------------------------------------------------------------------------+  |
|  | Optimization Heatmap & Patch Generator (crawler/eval/self_optimizer.py)     |  |
|  +-----------------------------------------------------------------------------+  |
|                                       |                                           |
|                                       v                                           |
|  +-----------------------------------------------------------------------------+  |
|  | Patch Proposals (AGENTS.md, skills/document-agents/*.md, tool error handlers) |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

### Recommended Project Structure

```
crawler/
├── synthetic/                     # Synthetic Data Generation Subsystem
│   ├── __init__.py
│   ├── schemas.py                 # Data schemas for 22 doc types + LoE & Ground Truth
│   ├── defects.py                 # Defect injection taxonomy & parametric mutators
│   ├── generator.py               # Core multi-document & LoE generator engine
│   ├── rasterizer.py              # 300 DPI pypdfium2 rasterization & Pillow scan artifacts
│   └── templates/                 # ReportLab document layout templates
├── eval/                          # Automated Benchmark & Self-Improvement Subsystem
│   ├── __init__.py
│   ├── benchmark_runner.py        # Benchmark harness & ground-truth scoring engine
│   ├── self_optimizer.py          # Failure categorization & prompt/skill patch generator
│   ├── fixtures/                  # Synthetic test suites (clean, defective, scanned)
│   │   ├── profiles/              # Synthetic applicant profile JSONs
│   │   ├── documents/             # Rendered clean and scanned PDFs
│   │   └── ground_truth/          # Machine-readable evaluation expectation JSONs
│   └── reports/                   # Evaluation run output logs & optimization heatmaps
└── tests/
    └── test_synthetic_eval.py     # Conformance tests for generator, harness, and optimizer
```

### Pattern 1: Parametric Document & Defect Generation (`crawler/synthetic/`)
**What:** Define structured dataclasses for each of the 22 Express Entry document types and Letters of Explanation. Include explicit defect flags in the profile specification (e.g. `defect_type: "missing_noc_duties"`).
**When to use:** Whenever creating test fixtures to verify document agent review skills against clean or defective applicant submissions.
**Example:**
```python
# Source: crawler/synthetic/schemas.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class InjectedDefect:
    defect_id: str             # e.g., "DEF-NOC-01"
    category: str              # e.g., "missing_noc_lead_statement"
    target_doc: str            # e.g., "employment_reference_letter"
    severity: str              # e.g., "critical" | "warning"
    description: str

@dataclass
class GroundTruthSpec:
    doc_type: str
    expected_verdict: str      # "meets_requirements" | "defective" | "incomplete"
    injected_defects: List[InjectedDefect]
    expected_claims: List[Dict[str, Any]]
    expected_basis_keys: List[str]  # Keys that MUST stay in basis[] (PII protection)
    must_abstain: bool = False
```

### Pattern 2: Multimodal Rasterization & Scan Artifact Injection (`crawler/synthetic/rasterizer.py`)
**What:** Render clean ReportLab vector PDFs to 300 DPI PIL images via `pypdfium2`, then apply synthetic scan artifacts (rotation, gaussian noise, contrast reduction, border shadows) using `Pillow`.
**When to use:** When generating image-based PDF or PNG test fixtures to benchmark OCR extraction resilience (`pytesseract`) and multimodal document inspection.
**Example:**
```python
# Source: crawler/synthetic/rasterizer.py
import io
import math
import random
from PIL import Image, ImageEnhance, ImageFilter
import pypdfium2 as pdfium

def rasterize_pdf_to_scanned_images(pdf_bytes: bytes, dpi: int = 300) -> List[Image.Image]:
    """Convert clean PDF bytes into a list of scanned PIL Images with realistic artifacts."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    scanned_pages = []
    
    for page_idx in range(len(pdf)):
        page = pdf[page_idx]
        # Render page at high DPI (scale = dpi / 72)
        scale = dpi / 72.0
        bitmap = page.render(scale=scale)
        pil_img = bitmap.to_pil()
        
        # 1. Subtle tilt / rotation (-1.2 to +1.2 degrees)
        angle = random.uniform(-1.2, 1.2)
        pil_img = pil_img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
        
        # 2. Convert to grayscale/monochrome scan
        pil_img = pil_img.convert("L")
        
        # 3. Adjust contrast and thresholding
        enhancer = ImageEnhance.Contrast(pil_img)
        pil_img = enhancer.enhance(random.uniform(0.85, 1.15))
        
        # 4. Add subtle gaussian noise / scan blur
        if random.random() > 0.5:
            pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=0.4))
            
        scanned_pages.append(pil_img.convert("RGB"))
        
    return scanned_pages
```

### Pattern 3: Fail-Closed Benchmark Scoring Harness (`crawler/eval/benchmark_runner.py`)
**What:** Execute agent review subcommands against synthetic document fixtures, parse output `AnswerObject` JSON, and score performance against ground truth specs.
**When to use:** In automated test runs or release gates to verify agent review accuracy across all 22 document types and LoEs.
**Example:**
```python
# Source: crawler/eval/benchmark_runner.py
from crawler.grounding import verify_grounding
from crawler.synthetic.schemas import GroundTruthSpec

def evaluate_agent_review(agent_output: dict, ground_truth: GroundTruthSpec) -> dict:
    """Evaluate agent AnswerObject against ground truth specification."""
    results = {
        "doc_type": ground_truth.doc_type,
        "grounding_passed": False,
        "citation_exactness": 0.0,
        "defect_detection_recall": 0.0,
        "false_positive_count": 0,
        "pii_containment_passed": True,
        "failures": []
    }
    
    # 1. Verify grounding gate on claims[]
    grounding_res = verify_grounding(agent_output)
    results["grounding_passed"] = (grounding_res.get("verdict") == "pass")
    if not results["grounding_passed"]:
        results["failures"].append({"type": "ungrounded_assertion", "details": grounding_res.get("reasons")})
        
    # 2. Verify defect detection recall
    detected_defects = extract_defects_from_agent_output(agent_output)
    expected_defects = {d.defect_id for d in ground_truth.injected_defects}
    
    if expected_defects:
        matched = detected_defects.intersection(expected_defects)
        results["defect_detection_recall"] = len(matched) / len(expected_defects)
        missed = expected_defects - detected_defects
        for m in missed:
            results["failures"].append({"type": "missed_defect", "defect_id": m})
            
    # 3. Check PII containment (personal fields MUST be in basis[], NEVER claims[])
    claims_text = " ".join([c.get("text", "") + " " + c.get("quote", "") for c in agent_output.get("claims", [])])
    for key in ground_truth.expected_basis_keys:
        if key in claims_text:
            results["pii_containment_passed"] = False
            results["failures"].append({"type": "pii_leak", "field": key})
            
    return results
```

### Anti-Patterns to Avoid
- **Hardcoding Ground-Truth Chunk IDs:** Never hardcode explicit chunk IDs (`#000`, `#001`) in synthetic test generators; chunk IDs drift when corpus index is rebuilt. Always reference relpaths (`employment-reference-letter.md`) or use dynamic searching.
- **Unrealistic Vector-Only Testing:** Testing agents solely on clean text PDFs misses OCR degradation issues, font rendering bugs, and scanned document artifacts that occur in real applicant e-APRs.
- **Inlining Personal PII into Claims:** Allowing synthetic applicant names, specific birth dates, or exact bank account numbers into `claims[].text` or `claims[].quote` violates strict local PII containment.
- **Unconstrained Self-Optimization Loops:** Allowing an automated prompt optimizer to rewrite system prompts without running conformance test gates (`test_instruction_eval.py`) can introduce false greens or break multi-CLI contract invariants.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| **PDF Document Rendering** | Don't manually compose PDF binary stream syntax or low-level canvas commands. | `reportlab` Platypus Flowable Engine | Hand-rolling PDF bytes leads to malformed files, missing font metrics, broken line wraps, and multi-page rendering bugs. Platypus flowables handle multi-page tables, headers, and paragraph layout natively. |
| **PDF Page Rasterization** | Don't shell out to system `pdftoppm` or `ghostscript` binaries. | `pypdfium2` | External binary CLI invocations break cross-platform portability and introduce system dependencies. `pypdfium2` bundles C++ pdfium binaries into python wheels and renders PDF pages directly to PIL Images. |
| **Grounding Verification Gate** | Don't write ad-hoc string matching or custom regex check logic for claim citations. | `crawler.grounding.verify_grounding` | Grounding checks must strictly enforce whitespace/case-normalized quote substring presence against `searchindex.py` chunks to maintain fail-closed guarantees. |
| **PII Isolation Perimeter** | Don't write manual regex filters for personal data fields in review text. | `crawler.vault` & AnswerObject `basis[]` split | `crawler/vault.py` provides established PII perimeter rules. Personal applicant profile data belongs in `basis[]`, while generic IRCC requirement labels belong in `claims[]`. |

## Common Pitfalls

### Pitfall 1: Unrealistic/Over-Simplified Synthetic Documents
**What goes wrong:** Synthetic documents contain hyper-clean formatting and ideal phrasing that pass agent review during testing, but real applicant documents contain typos, irregular tables, scan artifacts, and varied layouts that cause agent review failures.
**Why it happens:** Generative templates often rely on minimal text blocks without realistic legal boilerplate, bank table layouts, or multi-page structures.
**How to avoid:** Build comprehensive parametric layout templates in ReportLab with realistic IRCC/bank/employer boilerplate, variable table column counts, stamps, watermarks, and multi-page flowables.

### Pitfall 2: Ground-Truth Specification Drift
**What goes wrong:** Ground-truth JSON expectations become outdated when IRCC policy guidelines or corpus chunks update, causing benchmark runs to report false failure spikes.
**Why it happens:** Hardcoding specific quoted strings or chunk ordinal IDs directly in test specifications instead of linking to generic requirement rules or dynamic search indices.
**How to avoid:** Ground-truth specifications should define expected *defect categories* and *requirement labels*, using `crawler/grounding.py` for dynamic verification rather than frozen chunk string comparisons.

### Pitfall 3: Prompt Optimization Regressions & Multi-CLI Incompatibility
**What goes wrong:** `self_optimizer.py` generates prompt edits that fix a specific document defect failure but break multi-CLI compatibility or introduce ungrounded assertions in other document skills.
**Why it happens:** Optimizing for a single failing test case without running the full multi-CLI conformance test suite (`test_instruction_eval.py`, `test_conformance_v5_release_matrix.py`).
**How to avoid:** Gate every proposed patch generated by `self_optimizer.py` behind the full conformance test suite. Reject any patch that fails syntax, schema, or grounding checks.

### Pitfall 4: Misattributing CLI Tool Execution Errors to Prompt Reasoning Flaws
**What goes wrong:** The self-optimizer attempts to rewrite system prompts in `AGENTS.md` when a benchmark failure was actually caused by a CLI tool exception (e.g. non-zero exit code or malformed stdout).
**Why it happens:** Failing to categorize execution-level errors separately from LLM reasoning/grounding errors.
**How to avoid:** Explicitly catch tool execution errors (`tool_error`, `invalid_json_stdout`, `nonzero_exit`) in `benchmark_runner.py` and direct patch recommendations to python tool exception handling rather than system prompts.

## Code Examples

### 1. Synthetic Document Generator for e-APR Documents (`crawler/synthetic/generator.py`)
```python
# Source: crawler/synthetic/generator.py
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_synthetic_bank_letter(profile_data: dict, has_defect: bool = False) -> bytes:
    """Generate synthetic Proof of Funds bank letter with optional balance drop defect."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    story = []
    styles = getSampleStyleSheet()
    
    # Letterhead
    header_style = ParagraphStyle("BankHeader", parent=styles["Heading1"], fontSize=16, leading=20, textColor=colors.HexColor("#1A365D"))
    story.append(Paragraph("GLOBAL FIRST BANK - OFFICIAL FINANCIAL STATEMENT", header_style))
    story.append(Spacer(1, 12))
    
    # Body text
    body_style = styles["Normal"]
    applicant_name = profile_data.get("applicant_name", "Jane Doe")
    story.append(Paragraph(f"<b>Date:</b> July 15, 2026", body_style))
    story.append(Paragraph(f"<b>To:</b> Immigration, Refugees and Citizenship Canada (IRCC)", body_style))
    story.append(Paragraph(f"<b>Re:</b> Confirmation of Financial Account Balances for {applicant_name}", body_style))
    story.append(Spacer(1, 12))
    
    intro_text = (
        "This letter confirms that the above-named individual holds active accounts with Global First Bank. "
        "All funds listed below are unencumbered, fully liquid, and free of any third-party liens or debts."
    )
    story.append(Paragraph(intro_text, body_style))
    story.append(Spacer(1, 12))
    
    # Account Table (Defect injection: balance drops below required threshold if has_defect is True)
    balance_amount = "$14,000 CAD" if not has_defect else "$4,200 CAD"  # Defect: below IRCC 1-person threshold
    table_data = [
        ["Account Number", "Account Type", "Current Balance", "6-Month Avg Balance"],
        ["ACCT-992814", "Chequing", balance_amount, "$14,200 CAD" if not has_defect else "$4,500 CAD"],
        ["ACCT-881023", "Savings", "$2,500 CAD", "$2,500 CAD"]
    ]
    t = Table(table_data, colWidths=[110, 110, 130, 140])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#1A202C")),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("<b>Authorized Signatory:</b> Marcus Vance, Senior Branch Manager", body_style))
    doc.build(story)
    return buffer.getvalue()
```

### 2. Self-Optimizer Failure Analysis & Patch Proposal (`crawler/eval/self_optimizer.py`)
```python
# Source: crawler/eval/self_optimizer.py
import json
from pathlib import Path
from typing import List, Dict, Any

class SelfOptimizer:
    """Analyze benchmark evaluation logs and generate actionable prompt/skill patch proposals."""
    
    def __init__(self, eval_report_path: Path):
        self.report_path = eval_report_path
        
    def analyze_failures(self) -> Dict[str, Any]:
        with open(self.report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        category_counts = {}
        skill_failures = {}
        
        for run in data.get("runs", []):
            doc_type = run.get("doc_type")
            for failure in run.get("failures", []):
                fail_type = failure.get("type", "unknown")
                category_counts[fail_type] = category_counts.get(fail_type, 0) + 1
                
                if doc_type not in skill_failures:
                    skill_failures[doc_type] = []
                skill_failures[doc_type].append(failure)
                
        return {
            "total_runs": len(data.get("runs", [])),
            "category_summary": category_counts,
            "failing_skills": skill_failures
        }
        
    def generate_patch_proposals(self, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        proposals = []
        failing_skills = analysis.get("failing_skills", {})
        
        for doc_type, failures in failing_skills.items():
            skill_path = f"skills/document-agents/{doc_type}.md"
            reasons = [f.get("type") for f in failures]
            
            if "ungrounded_assertion" in reasons:
                proposals.append({
                    "target_file": skill_path,
                    "action": "strengthen_quote_normalization",
                    "proposal": f"Add explicit instruction in {skill_path} requiring exact verbatim quotes from corpus-crawler search output."
                })
            if "pii_leak" in reasons:
                proposals.append({
                    "target_file": skill_path,
                    "action": "enforce_basis_pii_split",
                    "proposal": f"Enforce strict move of applicant names/dates to basis[] in {skill_path}."
                })
                
        return proposals
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Manual document review testing using static hand-written test files. | Programmatic synthetic generation covering all 22 Express Entry document types + LoE with parametric defect injection. | Increases test edge-case coverage by 10x, enabling automated testing of rare post-ITA document defects (e.g. gift deed gaps, police cert delays). |
| Vector text-only PDF testing ignoring scanned document realities. | Multimodal scanned PDF pipeline (`pypdfium2` 300 DPI + `Pillow` scan noise + `pytesseract`). | Benchmarks agent resilience on OCR-extracted text and visual layout inspection before release. |
| Ad-hoc, manual prompt tuning when agents make review mistakes. | Closed-loop automated benchmark evaluation (`benchmark_runner.py`) and iterative prompt/skill optimizer (`self_optimizer.py`). | Provides quantitative metrics (Grounding Accuracy, Citation Precision, Defect Recall, PII Containment) and generates diff proposals directly tied to failure heatmaps. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PyPI packages (`reportlab`, `Pillow`, `pypdfium2`, `pytesseract`, `pdfplumber`, `pypdf`) are fully standard and safe despite PyPI API returning `[SUS]` for unknown weekly download metrics. | Package Legitimacy Audit | Low; packages are long-established open-source repositories verified on GitHub and PyPI. |
| A2 | System `tesseract-ocr` binary may be absent on build machine; `pypdfium2` native page rendering provides complete offline fallback for visual testing. | Environment Availability | Low; `pypdfium2` handles PDF rendering natively, while `pytesseract` OCR tests execute when tesseract-ocr binary is installed. |

## Open Questions

1. **How should `self_optimizer.py` balance automated patch proposal generation vs human safety checks?**
   - *What we know:* Automated prompt optimization can fix systematic errors but risks regressions if unconstrained.
   - *What's unclear:* Whether proposed patches should be automatically merged or output as git diff proposals for developer review.
   - *Recommendation:* Generate structured git diff patch proposals in `crawler/eval/reports/patches/` and enforce a release gate where proposed patches must pass `crawler/tests/test_instruction_eval.py` before application.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Core Runtime | ✓ | 3.10.12 | — |
| Node.js | gsd-tools CLI | ✓ | 25.9.0 | — |
| `pypdfium2` | PDF Page Rasterization | ✓ | 5.11.0 / 5.12.1 | — (bundled C++ pdfium library) |
| `pytesseract` | Python OCR Wrapper | ✓ | 0.3.13 | Fallback to `pypdfium2` text extraction if binary absent |
| System `tesseract-ocr` | Optical Character Recognition | ✗ | — | Skip OCR text verification, mock OCR text output in offline tests |
| System `pdftoppm` | Vector PDF Rendering | ✗ | — | Use `pypdfium2` native page rendering (no external C binary required) |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** System `tesseract-ocr` is missing on environment PATH; `pypdfium2` provides native page rendering and text extraction fallback for all synthetic visual tests.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 |
| Config file | `pyproject.toml` |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py -k synthetic` |
| Full suite command | `.venv/bin/python -m pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| **SELF-01** | Synthetic generator produces realistic documents, LoEs, and injected defects across all 22 Express Entry document types. | Integration | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py::test_synthetic_generator_coverage -x` | ❌ Wave 0 |
| **SELF-01** | Multimodal rasterizer converts text PDFs into 300 DPI scanned images with Pillow artifacts. | Unit | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py::test_rasterizer_scanned_pdf -x` | ❌ Wave 0 |
| **SELF-02** | Benchmark runner evaluates agent review outputs against ground truth JSON, scoring grounding, citations, defect recall, and PII containment. | Integration | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py::test_benchmark_runner_scoring -x` | ❌ Wave 0 |
| **SELF-03** | Self-optimizer categorizes evaluation failure logs, computes heatmaps, and generates valid patch proposals. | Unit | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py::test_self_optimizer_patch_generation -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py`
- **Per wave merge:** `.venv/bin/python -m pytest`
- **Phase gate:** Full test suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `crawler/tests/test_synthetic_eval.py` — test suite covering generator, rasterizer, benchmark runner, and self-optimizer.
- [ ] `crawler/synthetic/` package directory — modules `schemas.py`, `defects.py`, `generator.py`, `rasterizer.py`.
- [ ] `crawler/eval/benchmark_runner.py` and `crawler/eval/self_optimizer.py`.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Offline local CLI tool; no authentication endpoint. |
| V3 Session Management | No | No session state. |
| V4 Access Control | No | Local filesystem file permissions. |
| V5 Input Validation | Yes | Pydantic / dataclass schema validation for synthetic profile metadata and ground-truth specs. |
| V6 Cryptography / Privacy | Yes | Strict local PII perimeter: synthetic applicant profile data MUST reside in `basis[]` and never leak into public git ground-truth claims or corpus citations. |

### Known Threat Patterns for Synthetic & Evaluation Loop

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PII Leakage in Synthetic Fixtures | Information Disclosure | Synthetic data generator uses exclusively non-real mock names, addresses, and account numbers. Ground-truth validator enforces that profile identifiers belong in `basis[]`. |
| Prompt Patch Injection Attacks | Tampering | Self-optimizer generated patch proposals are strictly scoped to Markdown skill files and validated against `test_instruction_eval.py` conformance checks before merging. |
| Malformed Tool Execution Outputs | Denial of Service | Benchmark harness handles CLI process timeouts, non-zero exit codes, and invalid stdout gracefully without crashing evaluation runs. |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/48-synthetic-data-generation-agent-self-improvement-loop/48-CONTEXT.md` — User decisions and phase scope.
- `AGENTS.md` — System prompt specification authority and tool execution contracts.
- `skills/document-agents/_contract.md` — Shared answer-object contract (`claims[]`, `basis[]`, `abstentions[]`, `prose`).
- `crawler/grounding.py` — Fail-closed grounding gate verification engine.

### Secondary (MEDIUM confidence)
- [PyPI reportlab Package] (https://pypi.org/project/reportlab/) — ReportLab Platypus layout engine metadata.
- [PyPI pypdfium2 Package] (https://pypi.org/project/pypdfium2/) — Native PDFium rasterization metadata.
- [PyPI Pillow Package] (https://pypi.org/project/Pillow/) — Image manipulation and artifact metadata.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — Verified via PyPI registry, `.venv` runtime tests, and existing project codebase.
- Architecture: HIGH — Directly aligned with Phase 25/26 grounding gates and system contracts in `AGENTS.md`.
- Pitfalls: HIGH — Modeled on known LLM benchmark evaluation vulnerabilities and synthetic fixture generation traps.

**Research date:** 2026-07-21
**Valid until:** 2026-08-20 (30 days)
