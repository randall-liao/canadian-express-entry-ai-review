# Phase 72: Per-Document Research Agents (Gemini 3.6 Flash long context) - Pattern Map

**Mapped:** 2026-07-22
**Files analyzed:** 4 (1 runner modified/hardened, 2 new test modules, 1 research artifact schema)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `crawler/eval/doc_researcher.py` | service / agent runner | I-O / CLI execution | `crawler/eval/real_worker.py` | exact role-match |
| `crawler/tests/test_doc_researcher.py` | test | request-response / assertions | `crawler/tests/test_real_llm_engine.py` | exact role-match |
| `crawler/tests/test_doc_research_conformance.py` | test / conformance | batch / validation | `crawler/tests/test_conformance_v5_release_matrix.py` | role-match |
| `crawler/eval/pipelines/<doc_type>/research/research.json` | data artifact / schema | I-O / JSON | `skills/document-agents/_contract.md` & `crawler/synthetic/schemas.py` | exact schema-match |

---

## Pattern Assignments

### `crawler/eval/doc_researcher.py` (service / agent runner)

**Analog:** `crawler/eval/real_worker.py` & `crawler/eval/real_judge.py`

**Imports & Executable Discovery Pattern** (analog: `crawler/eval/real_worker.py` lines 1-25):
```python
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from crawler.synthetic.schemas import ExpressEntryDocType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"
_RESEARCH_MODEL = "gemini-3.6-flash"
_LLM_TIMEOUT_SECONDS = 300

# Executable discovery via env/PATH rather than hardcoded path
_COPILOT_PATH = (
    os.getenv("COPILOT_PATH")
    or shutil.which("copilot")
)
if not _COPILOT_PATH:
    raise RuntimeError("GitHub Copilot CLI executable not found")
```

**Copilot Invocation with Dependency Injection & Provenance** (analog: `crawler/eval/real_worker.py` lines 161-218):
```python
def research_document_failure_modes(
    doc_type: str,
    *,
    copilot_runner: Optional[Callable[[List[str], Path], subprocess.CompletedProcess]] = None,
) -> Dict[str, Any]:
    """Execute Gemini 3.6 Flash long-context research on failure modes for a specific document type.
    
    Fail closed if execution fails or output is malformed. Never emit fake success research.
    """
    pipeline_dir = _PIPELINES_DIR / doc_type / "research"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    out_path = pipeline_dir / "research.json"
    error_path = pipeline_dir / "research.error.json"

    prompt = _build_research_prompt(doc_type)
    command = [
        _COPILOT_PATH,
        "-p",
        prompt,
        "--model",
        _RESEARCH_MODEL,
        "-s",
    ]

    try:
        if copilot_runner is not None:
            result = copilot_runner(command, _REPO_ROOT)
        else:
            result = subprocess.run(
                command,
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=_LLM_TIMEOUT_SECONDS,
                check=False,
            )

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "no output").strip()
            raise CopilotExecutionError(
                f"Gemini Research Agent exited with code {result.returncode}: {detail[:2000]}"
            )

        data = _extract_json_object(result.stdout, required_keys={"doc_type", "failure_modes"})
        _validate_research_schema(data, doc_type)
        
        data["execution"] = {
            "status": "success",
            "engine": "copilot-cli",
            "model": _RESEARCH_MODEL,
            "timestamp": _utc_now(),
            "returncode": result.returncode,
        }
        _write_json(out_path, data)
        error_path.unlink(missing_ok=True)
        return data

    except Exception as exc:
        _record_research_failure(pipeline_dir, doc_type, exc)
        raise CopilotExecutionError(f"Research failed for {doc_type}: {exc}") from exc
```

**Fail-Closed Blocked State Pattern** (analog: `crawler/eval/real_worker.py` lines 143-158):
```python
def _record_research_failure(pipeline_dir: Path, doc_type: str, exc: BaseException) -> None:
    """Record explicit blocked/failed state without fabricating success."""
    out_path = pipeline_dir / "research.json"
    out_path.unlink(missing_ok=True)  # Remove stale/fake success artifacts
    error_data = {
        "doc_type": doc_type,
        "execution": {
            "status": "failed",
            "engine": "copilot-cli",
            "model": _RESEARCH_MODEL,
            "timestamp": _utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
        "passed": False,
    }
    _write_json(pipeline_dir / "research.error.json", error_data)
```

**JSON Schema Validation Pattern** (analog: `crawler/eval/real_worker.py` lines 42-106 & `crawler/eval/real_judge.py` lines 195-223):
```python
def _validate_research_schema(data: Dict[str, Any], expected_doc_type: str) -> None:
    if data.get("doc_type") != expected_doc_type:
        raise ValueError(f"doc_type mismatch: expected {expected_doc_type}, got {data.get('doc_type')}")
    failure_modes = data.get("failure_modes")
    if not isinstance(failure_modes, list) or len(failure_modes) < 3:
        raise ValueError(f"failure_modes must be a list with at least 3 entries, got {len(failure_modes) if isinstance(failure_modes, list) else type(failure_modes)}")
    
    required_keys = {"failure_id", "category", "severity", "title", "ircc_citation", "description", "defective_fields", "remediation"}
    for idx, mode in enumerate(failure_modes):
        if not isinstance(mode, dict):
            raise ValueError(f"failure_mode[{idx}] is not an object")
        missing = required_keys.difference(mode)
        if missing:
            raise ValueError(f"failure_mode[{idx}] missing required keys: {sorted(missing)}")
```

---

### `crawler/tests/test_doc_researcher.py` (test)

**Analog:** `crawler/tests/test_real_llm_engine.py`

**Unit Testing Copilot Runner & Fail-Closed Behavior** (analog: `crawler/tests/test_real_llm_engine.py` lines 39-82):
```python
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from crawler.eval import doc_researcher

class TestDocResearcher(unittest.TestCase):
    def test_parses_fenced_research_json(self) -> None:
        raw_output = "Research complete.\n```json\n" + json.dumps(_valid_research_payload()) + "\n```"
        parsed = doc_researcher._extract_json_object(raw_output, required_keys={"doc_type", "failure_modes"})
        self.assertEqual(parsed["doc_type"], "passport")

    @mock.patch("crawler.eval.doc_researcher.subprocess.run")
    def test_blocked_pipeline_no_fallback(self, run: mock.Mock) -> None:
        """Verify that CLI failure raises exception and records failed status, never fallback success."""
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="copilot connection error"
        )
        with self.assertRaises(doc_researcher.CopilotExecutionError):
            doc_researcher.research_document_failure_modes("passport")

    def test_injected_copilot_runner_test_double(self) -> None:
        """Verify explicit dependency injection for test doubles."""
        def mock_runner(cmd, cwd):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=json.dumps(_valid_research_payload()), stderr=""
            )
        result = doc_researcher.research_document_failure_modes("passport", copilot_runner=mock_runner)
        self.assertEqual(result["execution"]["status"], "success")
        self.assertEqual(result["execution"]["model"], "gemini-3.6-flash")
```

---

### `crawler/tests/test_doc_research_conformance.py` (test / conformance)

**Analog:** `crawler/tests/test_conformance_v5_release_matrix.py` & `crawler/tests/test_conformance_v41_coverage.py`

**23-Document Pipeline Conformance Pattern** (analog: `crawler/tests/test_conformance_v41_coverage.py`):
```python
import json
import unittest
from pathlib import Path
from crawler.synthetic.schemas import ExpressEntryDocType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"

class TestDocResearchConformance(unittest.TestCase):
    def test_all_23_document_types_have_isolated_valid_research(self) -> None:
        """Verify all 23 ExpressEntryDocTypes have authentic Gemini research artifacts."""
        doc_types = [dt.value for dt in ExpressEntryDocType]
        self.assertEqual(len(doc_types), 23)

        for doc_type in doc_types:
            research_file = _PIPELINES_DIR / doc_type / "research" / "research.json"
            self.assertTrue(
                research_file.is_file(),
                f"Missing research artifact for pipeline {doc_type}"
            )
            data = json.loads(research_file.read_text(encoding="utf-8"))
            execution = data.get("execution", {})
            self.assertEqual(execution.get("status"), "success", f"Research for {doc_type} is not success status")
            self.assertEqual(execution.get("model"), "gemini-3.6-flash", f"Research for {doc_type} missing gemini model metadata")
            self.assertGreaterEqual(len(data.get("failure_modes", [])), 3)
```

---

## Shared Patterns

### 1. GitHub Copilot CLI Invocation & Provenance Recording
**Source:** `crawler/eval/real_worker.py` lines 161-218 & `crawler/eval/real_judge.py` lines 240-282
**Apply to:** All model-backed agent runner modules (`doc_researcher.py`, `real_worker.py`, `real_judge.py`)
```python
# Production command construction
command = [
    _COPILOT_PATH,
    "-p", prompt,
    "--model", _RESEARCH_MODEL,
    "-s",
]

# Provenance metadata recorded on success
"execution": {
    "status": "success",
    "engine": "copilot-cli",
    "model": _RESEARCH_MODEL,
    "timestamp": _utc_now(),
    "returncode": result.returncode,
}
```

### 2. Executable Discovery via Env / PATH
**Source:** `crawler/eval/real_worker.py` line 17 & REVIEW.md WR-01
**Apply to:** All CLI sub-process invocations
```python
import os
import shutil

_COPILOT_PATH = (
    os.getenv("COPILOT_PATH")
    or shutil.which("copilot")
)
if not _COPILOT_PATH:
    raise RuntimeError("GitHub Copilot CLI executable not found")
```

### 3. Fail-Closed Blocked State (No Success-Shaped Fallbacks)
**Source:** `crawler/eval/real_worker.py` lines 143-158 & REVIEW.md CR-01
**Apply to:** `crawler/eval/doc_researcher.py`
```python
# Unlink previous success output and record explicit failure
out_path.unlink(missing_ok=True)
error_data = {
    "doc_type": doc_type,
    "execution": {
        "status": "failed",
        "engine": "copilot-cli",
        "model": _RESEARCH_MODEL,
        "timestamp": _utc_now(),
        "error_type": type(exc).__name__,
        "error": str(exc),
    },
    "passed": False,
}
_write_json(error_path, error_data)
raise CopilotExecutionError(f"Execution failed for {doc_type}: {exc}") from exc
```

### 4. Corpus-Crawler 5-Key Envelope Parsing
**Source:** `skills/document-agents/_contract.md` lines 46-56
**Apply to:** Grounding and search verification calls in local corpus
```json
{
  "schema_version": "1.0",
  "ok": true,
  "command": "ground",
  "result": { ... },
  "error": null
}
```

### 5. Bounded Concurrency across Isolated Document Pipelines
**Source:** `72-CONTEXT.md` D-01, D-03
**Apply to:** `research_all_document_types()` in `doc_researcher.py`
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def research_all_document_types(max_workers: int = 4) -> Dict[str, Dict[str, Any]]:
    doc_types = [dt.value for dt in ExpressEntryDocType]
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dt = {
            executor.submit(research_document_failure_modes, dt): dt
            for dt in doc_types
        }
        for future in as_completed(future_to_dt):
            dt = future_to_dt[future]
            results[dt] = future.result()
    return results
```

---

## Anti-Patterns to NOT Copy (Legacy Code Defects)

| Legacy Anti-Pattern | Found In (DO NOT COPY) | Correct Replacement |
|---------------------|------------------------|---------------------|
| **Silent Success-Shaped Fallback** | `doc_researcher.py:130-161`, `pipeline_worker.py:117-143` | Raise `CopilotExecutionError`, record `status: "failed"` in `<doc_type>.error.json`, unlink stale success JSON. |
| **Ground Truth Answer-Key Leakage** | `agent_improvement_loop.py:88-146`, `benchmark_runner.py:239-282` | Evaluate blind document text only; never inspect `ground_truth.get("injected_defects")` in worker/research roles. |
| **False LLM Model Metadata** | `doc_synthetic_generator.py:1-160`, `parallel_judge.py:269-290` | Never label Python script/regex output as `gemini-3.6-flash`, `gpt-5.6-sol`, or `claude-opus-4.8`. |
| **Broad Exception Swallowing** | `doc_researcher.py:129` (`except Exception:`) | Log error, record failure JSON, and re-raise explicit `CopilotExecutionError`. |
| **`--allow-all` from Repository Root for Blind Workers** | `pipeline_worker.py:88-92`, `doc_researcher.py:99-103` | Execute in isolated sandbox working directory containing only assigned pipeline files; do not expose `_REPO_ROOT`. |

---

## Metadata

**Analog search scope:** `crawler/eval/`, `crawler/tests/`, `skills/document-agents/`, `crawler/synthetic/`
**Files scanned:** 19
**Pattern extraction date:** 2026-07-22
