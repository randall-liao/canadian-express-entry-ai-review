# Phase 73: Blind Synthetic Document Generation (Gemini 3.6 Flash long context) - Pattern Map

**Mapped:** 2026-07-23
**Files analyzed:** 5 target files (1 generator service module, 1 schema module, 2 test modules, pipeline synthetic fixtures/manifests)
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `crawler/eval/doc_synthetic_generator.py` | service / agent runner & rendering coordinator | I-O / Copilot CLI + ReportLab + pypdfium2 | `crawler/eval/doc_researcher.py` & `crawler/synthetic/generator.py` | exact role-match |
| `crawler/synthetic/schemas.py` | data schemas / Pydantic models | I-O / JSON schema validation | `crawler/eval/doc_researcher.py` (`ResearchReport`) & `crawler/synthetic/schemas.py` | exact schema-match |
| `crawler/tests/test_doc_synthetic_generator.py` | test / unit & integration | request-response / assertions | `crawler/tests/test_doc_researcher.py` & `crawler/tests/test_pdf_synthetic.py` | exact role-match |
| `crawler/tests/test_doc_synthetic_conformance.py` | test / live conformance gate | batch / validation | `crawler/tests/test_doc_research_conformance.py` | exact role-match |
| `crawler/eval/pipelines/<doc_type>/ground_truth/<opaque>.json` | data artifact / privileged ground truth | I-O / JSON | `crawler/eval/pipelines/<doc_type>/research/research.json` | exact schema-match |

---

## Pattern Assignments

### 1. Genuine Copilot JSONL Generator Runner (`doc_synthetic_generator.py`)

**Analog:** `crawler/eval/doc_researcher.py` (lines 160-230, 398-460)

**Copilot Command & Execution Pattern:**
Executes GitHub Copilot CLI with model `gemini-3.6-flash`, `long_context`, streaming disabled, JSON output format, and strict noninteractive isolation flags. Supports test double injection via `copilot_runner`.

```python
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"
_GENERATOR_MODEL = "gemini-3.6-flash"
_TIMEOUT_SECONDS = 300

def _discover_copilot_executable() -> str:
    exe = os.getenv("COPILOT_PATH") or shutil.which("copilot")
    if not exe or not os.access(exe, os.X_OK):
        raise RuntimeError("GitHub Copilot CLI executable not found or not executable")
    return exe

def run_document_generator_agent(
    doc_type: str,
    research_data: Dict[str, Any],
    *,
    copilot_runner: Optional[Callable[[List[str], Path], subprocess.CompletedProcess]] = None,
    pipeline_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute Gemini 3.6 Flash long-context document generation agent for a specific document type.
    
    Fail closed if execution fails or output is malformed.
    """
    root = pipeline_root or _PIPELINES_DIR
    pipeline_dir = root / doc_type
    gt_dir = pipeline_dir / "ground_truth"
    test_data_dir = pipeline_dir / "test_data"
    gt_dir.mkdir(parents=True, exist_ok=True)
    test_data_dir.mkdir(parents=True, exist_ok=True)

    copilot_exe = _discover_copilot_executable()
    prompt = _build_generator_prompt(doc_type, research_data)
    
    command = [
        copilot_exe,
        "-p", prompt,
        "--model", _GENERATOR_MODEL,
        "--context", "long_context",
        "--available-tools", "web_search,web_fetch",
        "--output-format", "json",
        "--stream", "off",
        "--allow-all-tools",
        "--allow-all-urls",
        "--disallow-temp-dir",
        "--no-ask-user",
        "--no-custom-instructions",
    ]

    is_live = copilot_runner is None
    engine = "copilot-cli" if is_live else "injected-test-runner"

    try:
        if copilot_runner is not None:
            result = copilot_runner(command, pipeline_dir)
        else:
            result = subprocess.run(
                command,
                cwd=str(pipeline_dir),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )

        if result.returncode != 0:
            raise CopilotExecutionError(f"Generator agent exited with code {result.returncode}: {result.stderr[:1000]}")

        # Parse JSONL event stream to locate final assistant payload
        spec_dict = _parse_jsonl_assistant_payload(result.stdout)
        spec = GenerationSpec.model_validate(spec_dict)
        _validate_generator_coverage(spec, research_data)

        # Provenance metadata
        execution_meta = {
            "status": "success",
            "engine": engine,
            "is_live": is_live,
            "model": _GENERATOR_MODEL,
            "timestamp": _utc_now_iso(),
            "duration_seconds": elapsed,
            "command": ["copilot", "--model", _GENERATOR_MODEL, "--context", "long_context"],
            "prompt_sha256": _sha256(prompt),
            "raw_output_sha256": _sha256(result.stdout),
            "returncode": result.returncode,
            "provenance_token": _sha256(f"{doc_type}:{_GENERATOR_MODEL}:{result.stdout}"),
        }
        return {"spec": spec, "execution": execution_meta}

    except Exception as exc:
        _record_generator_failure(pipeline_dir, doc_type, exc, engine=engine, is_live=is_live)
        raise CopilotExecutionError(f"Generation failed for {doc_type}: {exc}") from exc
```

---

### 2. Strict GenerationSpec Schemas (Agent-vs-Renderer Separation)

**Analog:** `crawler/eval/doc_researcher.py` (`ResearchReport`) & `crawler/synthetic/schemas.py` (`SyntheticDocument`)

**Agent-Authored Specification Schema Pattern:**
The agent is responsible for document content, narrative text, field values, layout intent, 1 valid control case, and 1 defective case per research failure mode (95 failure modes across 23 doc types = 118 logical cases = 236 PDFs). Deterministic Python code ONLY validates, renders, rasterizes, hashes, and stores the agent-authored specification.

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class CaseSpec(BaseModel):
    """Agent-authored specification for a single logical test case."""
    case_type: str = Field(description="'valid_control' or 'defective'")
    source_failure_id: Optional[str] = Field(None, description="Research failure ID (null for valid control)")
    fields: Dict[str, Any] = Field(description="Document fields authored by Gemini")
    narrative_content: Dict[str, Any] = Field(default_factory=dict, description="Custom narrative paragraphs or body text")
    layout_intent: Dict[str, Any] = Field(default_factory=dict, description="Header, logo, seal, or table structure intent")
    affected_fields: List[str] = Field(default_factory=list, description="Fields modified or omitted for defective case")

class GenerationSpec(BaseModel):
    """Agent-authored generation specification covering valid control + all research failure modes."""
    doc_type: str
    timestamp: str
    valid_control: CaseSpec
    defective_cases: List[CaseSpec] = Field(min_items=3, description="Must cover every failure mode in research.json")
```

---

### 3. Opaque IDs & Blind File Layout

**Analog:** `crawler/synthetic/generator.py` & `crawler/eval/doc_synthetic_generator.py`

**Cryptographic Opaque ID Pattern:**
Case IDs and filenames use cryptographically random hexadecimal strings (`secrets.token_hex(4)` -> e.g. `8f3a9b1c.pdf`). Filenames contain NO sequential numbers (`doc_001_vec`), NO variant indicators (`_vec`, `_scan`), NO document type (`passport`), and NO defect/verdict labels (`pfl_`, `defective`).

```python
import secrets

def generate_opaque_case_id() -> str:
    """Generate cryptographically opaque 8-character hex case identifier."""
    return secrets.token_hex(4)  # e.g., '8f3a9b1c'

def format_blind_filename(case_id: str) -> str:
    """Format uniform blind filename for worker exposure."""
    return f"{case_id}.pdf"  # e.g., '8f3a9b1c.pdf'
```

---

### 4. Private Ground Truth vs Worker-Visible Staging Input

**Analog:** `crawler/eval/doc_synthetic_generator.py` & `skills/document-agents/_contract.md`

**Privileged Manifest & Worker Staging Pattern:**
Ground truth files in `crawler/eval/pipelines/<doc_type>/ground_truth/<opaque_id>.json` hold all privileged metadata (research failure ID, affected fields, expected verdict, sibling links, hashes). Worker-visible staging (`stage_worker_case`) copies ONLY `<opaque_id>.pdf` and optional sanitized extracted text into a fresh, isolated directory outside the pipeline tree.

```python
def write_private_ground_truth(
    gt_dir: Path,
    case_id: str,
    sibling_case_id: str,
    doc_type: str,
    variant: str,  # "vector" | "scanned"
    expected_verdict: str,  # "meets_requirements" | "defective"
    source_failure_id: Optional[str],
    affected_fields: List[str],
    fields: Dict[str, Any],
    pdf_bytes: bytes,
    agent_spec_sha256: str,
) -> Path:
    gt_path = gt_dir / f"{case_id}.json"
    gt_data = {
        "case_id": case_id,
        "sibling_case_id": sibling_case_id,
        "doc_type": doc_type,
        "variant": variant,
        "blind_filename": f"{case_id}.pdf",
        "expected_verdict": expected_verdict,
        "source_failure_id": source_failure_id,
        "affected_fields": affected_fields,
        "fields": fields,
        "pdf_sha256": _sha256(pdf_bytes),
        "agent_spec_sha256": agent_spec_sha256,
        "timestamp": _utc_now_iso(),
    }
    gt_path.write_text(json.dumps(gt_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return gt_path

def stage_worker_case(
    doc_type: str,
    case_id: str,
    worker_target_dir: Path,
    pipeline_root: Optional[Path] = None,
) -> Path:
    """Stage a single blind PDF and allowed extracted text into fresh worker directory.
    
    Contains NO ground truth, research IDs, verdicts, or foreign pipeline files.
    """
    root = pipeline_root or _PIPELINES_DIR
    source_pdf = root / doc_type / "test_data" / f"{case_id}.pdf"
    if not source_pdf.is_file():
        raise FileNotFoundError(f"Source PDF for case {case_id} not found at {source_pdf}")

    worker_target_dir.mkdir(parents=True, exist_ok=True)
    staged_pdf = worker_target_dir / f"{case_id}.pdf"
    shutil.copy2(source_pdf, staged_pdf)
    return staged_pdf
```

---

### 5. Vector & 300 DPI Scanned Rendering & Sibling Pairing

**Analog:** `crawler/synthetic/generator.py` (`generate_synthetic_document`) & `crawler/synthetic/rasterizer.py` (`rasterize_pdf_to_scanned_pdf`)

**Rendering & Rasterization Pattern:**
Vector PDF is rendered from `CaseSpec` using ReportLab Platypus. Scanned sibling is generated by rasterizing vector PDF bytes to 300 DPI image via `pypdfium2`, applying rotation tilt and noise blur via Pillow, and re-assembling into image-only PDF with zero text layer.

```python
from crawler.synthetic.generator import generate_synthetic_document
from crawler.synthetic.rasterizer import rasterize_pdf_to_scanned_pdf

def render_case_pair(
    doc_type: str,
    case_spec: CaseSpec,
    test_data_dir: Path,
) -> Tuple[str, str, bytes, bytes]:
    """Render vector PDF and 300 DPI scanned sibling from single agent CaseSpec."""
    vec_id = generate_opaque_case_id()
    scan_id = generate_opaque_case_id()

    # Render clean vector PDF from agent specification
    vector_bytes = render_agent_spec_to_vector_pdf(doc_type, case_spec)
    
    # Rasterize clean vector bytes to 300 DPI scanned PDF sibling
    scanned_bytes = rasterize_pdf_to_scanned_pdf(
        vector_bytes,
        dpi=300,
        rotation_deg=1.0,
        add_noise=True,
    )

    # Write files with uniform blind names
    (test_data_dir / f"{vec_id}.pdf").write_bytes(vector_bytes)
    (test_data_dir / f"{scan_id}.pdf").write_bytes(scanned_bytes)

    return vec_id, scan_id, vector_bytes, scanned_bytes
```

---

### 6. Metadata Sanitization & Automated Leakage Scanning

**Analog:** `crawler/tests/test_pdf_synthetic.py` & `skills/pdf/SKILL.md`

**Sanitization & Leakage Scanner Pattern:**
Sanitize ReportLab PDF canvas metadata (title, author, producer set to blank/generic). Automated scanner inspects rendered PDF page text, metadata dicts, bookmarks, and filenames against forbidden privileged term regexes.

```python
import re
import pdfplumber

_FORBIDDEN_LEAKAGE_REGEXES = [
    re.compile(r"pfl[-_]?", re.IGNORECASE),
    re.compile(r"defect(ive)?", re.IGNORECASE),
    re.compile(r"passport|language_test|educational_credential|employment_reference", re.IGNORECASE),
    re.compile(r"missing_|expired_|unencumbered_|mismatch", re.IGNORECASE),
    re.compile(r"meets_requirements|expected_verdict", re.IGNORECASE),
    re.compile(r"ground_truth|research_notes|failure_mode", re.IGNORECASE),
]

def scan_pdf_for_privileged_leakage(pdf_bytes: bytes, filename: str) -> List[str]:
    """Scan PDF filename, metadata, and page text for privileged label leakage."""
    leakages = []

    # 1. Check filename
    for rx in _FORBIDDEN_LEAKAGE_REGEXES:
        if rx.search(filename):
            leakages.append(f"Filename '{filename}' leaked pattern: {rx.pattern}")

    # 2. Check metadata & page text
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for k, v in (pdf.metadata or {}).items():
            for rx in _FORBIDDEN_LEAKAGE_REGEXES:
                if rx.search(str(v)):
                    leakages.append(f"PDF metadata key '{k}'='{v}' leaked pattern: {rx.pattern}")

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for rx in _FORBIDDEN_LEAKAGE_REGEXES:
                if rx.search(text):
                    leakages.append(f"PDF page {page_num} text leaked pattern: {rx.pattern}")

    return leakages
```

---

### 7. Temporary-Root Unit/Integration Tests

**Analog:** `crawler/tests/test_doc_researcher.py` (lines 140-195)

**Temporary Root Testing Pattern:**
All non-live unit/integration tests (`test_doc_synthetic_generator.py`) execute using `tempfile.TemporaryDirectory()`, passing `pipeline_root=tmp_path`. Non-live test double runners produce `is_live=False` and `engine="injected-test-runner"`. Ordinary test runs NEVER seed or mutate `crawler/eval/pipelines/`.

```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

class TestDocSyntheticGenerator(unittest.TestCase):
    def test_generator_provenance_is_truthful(self) -> None:
        """Verify injected test double marks is_live=False and engine=injected-test-runner."""
        def mock_runner(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
            payload = _valid_generator_payload("passport")
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=_make_jsonl_response(payload), stderr=""
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            research_data = _valid_research_payload("passport")
            
            res = run_document_generator_agent(
                "passport",
                research_data,
                copilot_runner=mock_runner,
                pipeline_root=tmp_path,
            )

            execution = res["execution"]
            self.assertEqual(execution["status"], "success")
            self.assertEqual(execution["engine"], "injected-test-runner")
            self.assertFalse(execution["is_live"])
            self.assertEqual(execution["model"], "gemini-3.6-flash")
```

---

### 8. Live Conformance Gate & Stale-Artifact Cleanup

**Analog:** `crawler/tests/test_doc_research_conformance.py` (lines 113-290, 468-510)

**Conformance Gate & Fail-Closed Pattern:**
`test_doc_synthetic_conformance.py` enforces a live-only gate enabled via `REQUIRE_LIVE_SYNTHETIC_CONFORMANCE=1`. Validates all 23 document types, 118 logical cases, 236 vector/scanned PDFs, failure mode coverage, provenance (`is_live=True`, `engine="copilot-cli"`), and blind leakage scans. If execution fails, stale success files are unlinked and `<doc_type>.error.json` is recorded.

```python
def _record_generator_failure(
    pipeline_dir: Path,
    doc_type: str,
    exc: BaseException,
    engine: str = "copilot-cli",
    is_live: bool = True,
) -> None:
    """Unlink stale success artifacts and record explicit blocked failure state."""
    # Fail closed: clear stale ground_truth and test_data PDFs
    gt_dir = pipeline_dir / "ground_truth"
    test_data_dir = pipeline_dir / "test_data"
    if gt_dir.exists():
        for p in gt_dir.glob("*.json"):
            p.unlink(missing_ok=True)
    if test_data_dir.exists():
        for p in test_data_dir.glob("*.pdf"):
            p.unlink(missing_ok=True)

    error_data = {
        "doc_type": doc_type,
        "execution": {
            "status": "failed",
            "engine": engine,
            "is_live": is_live,
            "model": _GENERATOR_MODEL,
            "timestamp": _utc_now_iso(),
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
        "passed": False,
    }
    (pipeline_dir / "generator.error.json").write_text(
        json.dumps(error_data, indent=2), encoding="utf-8"
    )
```

---

## Anti-Patterns to NOT Copy (Legacy Defects in `doc_synthetic_generator.py`)

The following anti-patterns exist in legacy `doc_synthetic_generator.py` and MUST NOT be copied into Phase 73 implementation:

| Legacy Anti-Pattern | Location in Legacy Code | Why Prohibited | Phase 73 Replacement |
|---------------------|--------------------------|----------------|----------------------|
| **Deterministic Defect Selection** | `doc_synthetic_generator.py:55-70` (`if "translation" in cat: defect_categories.append(...)`) | Python code hardcodes defect rules rather than letting Gemini Flash author specifications based on research reports. | Gemini 3.6 Flash agent receives research report and authors full `GenerationSpec` covering valid control + every failure mode. |
| **Success-Shaped Fallbacks** | `doc_synthetic_generator.py:72-77` (`if not defect_categories: defect_categories = [...]`) | Fabricates default test cases when agent/research fails, violating truthful execution rules. | Raise `CopilotExecutionError`, record `generator.error.json`, unlink stale artifacts, fail pipeline closed. |
| **Sequential & Hint-Bearing Filenames** | `doc_synthetic_generator.py:92, 118` (`doc_001_vec.pdf`, `doc_001_scan.pdf`) | Sequential numbering and variant suffixes (`_vec`, `_scan`) leak case ordering and format hints to workers. | Cryptographically opaque IDs (`secrets.token_hex(4)`) and uniform `<opaque>.pdf` filenames with private linkage manifest. |
| **Public Research Notes Leakage** | `doc_synthetic_generator.py:109, 136` (`"research_notes": "Generated from research case..."`) | Exposes research failure mode labels and case origins in ground truth metadata accessible to workers. | Omit explanatory notes, failure labels, or verdict hints from worker-visible artifacts; store failure IDs strictly in private ground truth. |
| **False Gemini Labeling** | `doc_synthetic_generator.py:1-160` (Docstring claiming "derived from Gemini research findings" while executing purely deterministic Python) | Presents local Python/ReportLab script output as Gemini AI generation without live Copilot CLI execution. | True Gemini 3.6 Flash agent execution via Copilot CLI with full provenance (`is_live`, `model`, `prompt_sha256`, `raw_output_sha256`). |

---

## Metadata

**Analog search scope:** `crawler/eval/`, `crawler/synthetic/`, `crawler/tests/`, `skills/pdf/`
**Files scanned:** 14
**Pattern extraction date:** 2026-07-23
