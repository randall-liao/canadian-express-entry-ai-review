# Phase 72: Per-Document Research Agents (Gemini 3.6 Flash long context) - Research

**Researched:** 2026-07-22
**Domain:** Autonomous LLM Research Agents, Schema Validation, Grounded Policy Verification, Process Isolation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Launch exactly one dedicated research agent for each `ExpressEntryDocType`; agents must not combine document types or read another document type's pipeline.
- **D-02:** Every research agent uses `gemini-3.6-flash` with `long_context`. GPT 5.6 SOL XHIGH remains the top-level orchestrator, not a replacement for the per-document researchers.
- **D-03:** Agents may execute concurrently, but each writes only beneath `crawler/eval/pipelines/<doc_type>/research/`.
- **D-04:** Online sources may discover recurring failure patterns, refusal examples, and PFL triggers, but policy requirements must be verified against authoritative IRCC/Justice Laws sources and the local corpus before being represented as requirements.
- **D-05:** Each failure mode records a stable ID, category, severity, affected fields/evidence, source URL, retrieval date, exact supporting excerpt, authority classification, and remediation hypothesis.
- **D-06:** Anecdotal or third-party observations must be labeled as discovery evidence and kept distinct from authoritative policy evidence. Unsupported policy claims fail closed rather than being inferred.
- **D-07:** Research artifacts are privileged inputs for the synthetic generator and final Judge only. They must never be copied into blind PDFs, opaque filenames, worker prompts, extracted text, worker working directories, or worker-visible metadata.
- **D-08:** Research output uses a machine-readable schema plus a human-readable summary per document type so Phase 73 can generate fixtures deterministically without leaking defect labels to report-generating agents.
- **D-09:** Pipeline isolation is structural, not prompt-only: later worker processes receive a staged blind input directory that contains only the PDF and allowed extracted text.
- **D-10:** Live research failure, malformed output, missing citations, or insufficient coverage is an explicit failed/blocked document pipeline. Generic fallback findings must not masquerade as successful online research.
- **D-11:** Phase completion requires all 23 research reports to pass schema, source, citation, uniqueness, and cross-pipeline isolation validation.
- **D-12:** Every researcher role executes through a real GitHub Copilot CLI agent session; Python schedules, isolates, validates, and persists but does not fabricate research output.
- **D-13:** Production code must not derive role output from ground truth, emit deterministic output under a model label, append canned patches, or convert a failed Copilot call into success.
- **D-14:** Test doubles require explicit dependency injection, while production provenance records the actual Copilot command, model, execution status, and artifact origin.

### the agent's Discretion
- Query wording, bounded concurrency, retry timing, and the exact JSON field names are implementation details, provided they preserve the locked model, evidence, fail-closed, and isolation contracts above.

### Deferred Ideas (OUT OF SCOPE)
- Research-driven vector and scanned defective PDF generation - Phase 73.
- Blind report generation, privileged Judge evaluation, and prompt/skill self-improvement - Phase 74.
- End-to-end GPT 5.6 SOL XHIGH orchestration and root `TEST_REPORT.md` export - Phase 75.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOC_RESEARCH-01 | Run one dedicated Gemini 3.6 Flash long-context research agent for each of the 23 Express Entry document types and produce validated, source-rich failure-mode reports in isolated per-document pipeline directories. | Establishes the 23-agent architecture, `doc_researcher.py` refactoring, `Pydantic` schema enforcement, `corpus-crawler --json search` local grounding gate, bounded thread runner, and fail-closed blocked pipeline handling. [VERIFIED: Codebase / CONTEXT.md] |
| REAL_AGENT_EXECUTION-01 | Execute every claimed research role through a real GitHub Copilot CLI agent session and fail explicitly instead of substituting deterministic or hardcoded output. | Requires truthful Copilot provenance, explicit injected test doubles, removal of generic fallback generation, and live 23-agent completion evidence. [VERIFIED: CONTEXT.md / REVIEW.md] |
</phase_requirements>

## Summary

Phase 72 establishes dedicated, autonomous research agents powered by Gemini 3.6 Flash long context (`gemini-3.6-flash`) for all 23 Express Entry document types (`ExpressEntryDocType`). Each agent operates in total isolation, researching real-world IRCC failure cases, refusal reasons, Procedural Fairness Letter (PFL) triggers, and applicant mistakes online and in the local corpus.

Existing code in `crawler/eval/doc_researcher.py` provides an initial baseline, but contains critical gaps that violate decisions D-04, D-05, D-06, D-10, and D-11:
1. **Generic Fallback Research:** `doc_researcher.py` currently emits hardcoded generic fallback JSON when live Copilot execution or JSON parsing fails. This directly violates **D-10** ("Generic fallback findings must not masquerade as successful online research"). Live LLM or validation failures must fail closed as explicit blocked pipelines.
2. **Incomplete Schema:** The existing schema records only basic fields (`failure_id`, `category`, `severity`, `title`, `ircc_citation`, `description`, `defective_fields`, `remediation`). It lacks D-05 required fields: `authority_classification`, `source_url`, `retrieval_date`, `supporting_excerpt`, `remediation_hypothesis`, and local corpus verification attributes.
3. **Missing Grounded Policy Gate:** D-04/D-06 require third-party or anecdotal web claims to be labeled as `discovery` evidence, while policy assertions must be cross-checked against authoritative IRCC/Justice Laws sources and verified locally via `corpus-crawler --json search`.
4. **Serial Execution:** The baseline executes sequentially. Concurrency bounded by a thread pool (e.g. `max_workers=4`) accelerates full 23-agent runs while respecting Copilot CLI process bounds and pipeline directory isolation.

**Primary Recommendation:** Refactor `crawler/eval/doc_researcher.py` to remove generic fallback generation, enforce strict Pydantic/dataclass schema validation for failure modes, integrate `corpus-crawler --json search` verification, run bounded concurrent agent execution, emit both `research.json` and `research_summary.md` into `crawler/eval/pipelines/<doc_type>/research/`, and add comprehensive unit and conformance tests under `crawler/tests/`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| **Online Failure Discovery** | Live LLM Subagent (`gemini-3.6-flash` via Copilot CLI) | — | Discovers real-world refusal patterns, forum case studies, and PFL triggers across Express Entry document types. |
| **Authoritative Local Verification** | Local Corpus Grounding Gate (`corpus-crawler --json search`) | `corpus/index.db` | Grounding gate verifies policy assertions against official IRCC/Justice Laws chunks before classifying as authoritative. |
| **Schema Validation & Isolation** | Python Runner (`crawler/eval/doc_researcher.py`) | Pydantic / Dataclasses | Enforces D-05/D-06 schema completeness, unique IDs, blocked pipeline semantics, and structural directory bounds. |
| **Downstream Artifact Partition** | Pipeline Storage (`crawler/eval/pipelines/<doc_type>/research/`) | Phase 73 Generator / Phase 74 Judge | Stores privileged research manifests isolated from blind worker input staging. |

## Standard Stack

### Core
| Library / Tool | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| **Copilot CLI** | PATH-resolved `copilot` | Live LLM execution engine for `gemini-3.6-flash` | Established project standard for live model invocation across all milestones. [VERIFIED: Codebase] |
| **`corpus-crawler` CLI** | `2.0.0` (in `.venv`) | Local FTS5 corpus search & citation resolution | Standard project grounding interface; provides global `--json` 5-key envelope. [VERIFIED: AGENTS.md] |
| **Pydantic / Dataclasses** | `2.13.0` | Strongly typed schema definition and validation | Standard Python validation framework used across crawler models. [VERIFIED: pyproject.toml] |
| **`concurrent.futures`** | Python 3.10 standard library | Bounded thread pool execution for concurrent subagents | Native, process-safe concurrency management without external async overhead. [VERIFIED: Python Stdlib] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **`pytest`** | `9.0.3` | Unit and conformance test runner | Testing schema validation, isolation bounds, and blocked status handling. [VERIFIED: pyproject.toml] |
| **`json` / `pathlib`** | Python stdlib | File I/O, path manipulation, and envelope parsing | Writing isolated `research.json` and `research_summary.md` files. [VERIFIED: Python Stdlib] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `concurrent.futures.ThreadPoolExecutor` | `asyncio` / `ProcessPoolExecutor` | ThreadPoolExecutor is simpler for wrapping external `subprocess.run` calls without subshell overhead or pickle serialization issues. [VERIFIED: Python Stdlib] |
| Explicit Pydantic validator | Raw `jsonschema` library | Pydantic is already a core project dependency and integrates cleanly with Python typing. [VERIFIED: pyproject.toml] |

## Package Legitimacy Audit

No new external packages are installed for Phase 72. All tools and dependencies (`pydantic`, `pytest`, `pdfminer.six`, `pypdfium2`, `Pillow`, `pyyaml`, `platformdirs`) are already specified in `pyproject.toml` and verified in the environment.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `pydantic` | PyPI | 8+ yrs | >50M/wk | `github.com/pydantic/pydantic` | [OK] | Approved (existing core dependency) |
| `pytest` | PyPI | 10+ yrs | >30M/wk | `github.com/pytest-dev/pytest` | [OK] | Approved (existing test dependency) |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                              +--------------------------------------------------+
                              |         23 Express Entry Document Types          |
                              |             (ExpressEntryDocType)                |
                              +--------------------------------------------------+
                                                       |
                                                       v
                                    +------------------------------------+
                                    | ThreadPoolExecutor (max_workers=4) |
                                    +------------------------------------+
                                                       |
                      +--------------------------------+--------------------------------+
                      |                                |                                |
                      v                                v                                v
          +-----------------------+        +-----------------------+        +-----------------------+
          | Agent: passport       |        | Agent: language_test  |        | Agent: ... (23 total) |
          +-----------------------+        +-----------------------+        +-----------------------+
                      |                                |                                |
                      v                                v                                v
          Copilot CLI LLM Call             Copilot CLI LLM Call             Copilot CLI LLM Call
       (gemini-3.6-flash long-ctx)      (gemini-3.6-flash long-ctx)      (gemini-3.6-flash long-ctx)
                      |                                |                                |
                      v                                v                                v
             Raw Failure Modes                Raw Failure Modes                Raw Failure Modes
                      |                                |                                |
                      +--------------------------------+--------------------------------+
                                                       |
                                                       v
                                    +------------------------------------+
                                    | Local Corpus Grounding Gate        |
                                    | corpus-crawler --json search       |
                                    | (Verifies IRCC / IRPR policy claims) |
                                    +------------------------------------+
                                                       |
                                                       v
                                    +------------------------------------+
                                    | Pydantic Schema & ID Validator     |
                                    | (Enforces D-05/D-06/D-10/D-11)     |
                                    +------------------------------------+
                                           /                          \
                                 PASS     /                            \   FAIL / TIMEOUT
                                         v                              v
                      +-----------------------------------+   +-----------------------------------+
                      | Pipeline Research Manifest        |   | Explicit Blocked Pipeline Status  |
                      | - research.json                   |   | - research.json (status: blocked) |
                      | - research_summary.md             |   | - NO generic fallback research!   |
                      | Directory:                        |   +-----------------------------------+
                      | crawler/eval/pipelines/<type>/    |
                      |   research/                       |
                      +-----------------------------------+
```

### Recommended Project Structure

```
crawler/
├── eval/
│   ├── doc_researcher.py          # Refactored 23-agent research runner & schema validator
│   ├── doc_research_validator.py  # Optional separate validation helper module
│   └── pipelines/
│       ├── passport/
│       │   └── research/
│       │       ├── research.json         # Schema-validated JSON artifact
│       │       └── research_summary.md   # Human-readable summary
│       ├── language_test/
│       │   └── research/ ...
│       └── <23_doc_types>/
│           └── research/ ...
└── tests/
    ├── test_doc_researcher.py     # Unit tests with mock Copilot calls & schema validation
    └── test_doc_research_conformance.py # Conformance test for all 23 pipeline schemas
```

### Key Architectural Patterns

#### Pattern 1: Bounded Concurrent LLM Worker Pool
**What:** Execute subagents concurrently across the 23 document types using a `ThreadPoolExecutor` with a bounded concurrency cap (`max_workers=4`).
**When to use:** When running batch LLM calls via Copilot CLI to prevent process thrashing while maximizing throughput.
**Example:**
```python
# Source: Python concurrent.futures standard pattern
from concurrent.futures import ThreadPoolExecutor, as_completed

def research_all_document_types(max_workers: int = 4) -> Dict[str, Any]:
    doc_types = [dt.value for dt in ExpressEntryDocType]
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dt = {
            executor.submit(research_document_failure_modes, dt): dt
            for dt in doc_types
        }
        for future in as_completed(future_to_dt):
            dt = future_to_dt[future]
            try:
                results[dt] = future.result()
            except Exception as exc:
                results[dt] = {"status": "blocked", "error": str(exc), "doc_type": dt}
    return results
```

#### Pattern 2: Local Corpus Grounding Gate
**What:** Cross-check LLM policy assertions against `corpus/index.db` using `corpus-crawler --json search`.
**When to use:** For every failure mode identified during online research before marking its authority classification as `"authoritative"`.
**Example:**
```python
# Source: skills/document-agents/_contract.md
import subprocess, json

def verify_policy_assertion_locally(query: str) -> tuple[bool, List[str]]:
    cmd = [
        ".venv/bin/python", "-m", "crawler.cli",
        "--json", "search", query,
        "--db", "corpus/index.db",
        "--limit", "3"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode == 0 and res.stdout:
        envelope = json.loads(res.stdout)
        if envelope.get("ok") and envelope.get("result", {}).get("hits"):
            hits = envelope["result"]["hits"]
            chunk_ids = [h["id"] for h in hits if "id" in h]
            return True, chunk_ids
    return False, []
```

#### Pattern 3: Fail-Closed Blocked Pipeline Semantics
**What:** Mark the pipeline output as `"status": "blocked"` on live call, timeout, or schema failure, completely omitting generic fallbacks.
**When to use:** Satisfying D-10 to prevent synthetic/generic success-shaped data from masquerading as real research.

### Anti-Patterns to Avoid
- **Generic Success-Shaped Fallbacks:** Generating generic fallback JSON when an LLM call fails. **Violation of D-10.** Must record explicit blocked status.
- **Cross-Pipeline Storage Contamination:** Writing research outputs to a shared folder or reading another document type's pipeline. **Violation of D-01/D-03.**
- **Labeling Anecdotal Claims as Authoritative Policy:** Marking forum posts or unverified blog claims as `authoritative` without local corpus or official IRCC/Justice Laws citations. **Violation of D-04/D-06.**
- **Exposing Research Artifacts to Worker Prompts:** Staging `research.json` into blind worker workspaces in later phases. **Violation of D-07/D-09.**

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Local corpus searching | Custom SQLite FTS queries | `corpus-crawler --json search` | Guarantees consistent 5-key JSON envelope, BM25 ranking, and citation resolution semantics defined in `AGENTS.md`. [VERIFIED: AGENTS.md] |
| LLM execution | Custom HTTP client / REST requests | PATH-resolved Copilot CLI (`copilot -p ...`) | Project standard for model execution with built-in token management and model selection (`gemini-3.6-flash`). [VERIFIED: Codebase] |
| Schema enforcement | Manual dict key checking | `Pydantic` or `@dataclass` validation | Automatically validates required fields, types, enum bounds, and default values cleanly. [VERIFIED: pyproject.toml] |

## Common Pitfalls

### Pitfall 1: Success-Shaped Generic Fallbacks (D-10 Violation)
**What goes wrong:** When Copilot CLI fails, times out, or emits malformed output, the system returns pre-crafted generic failure modes so execution appears "successful".
**Why it happens:** Legacy baseline code in `doc_researcher.py` contains `fallback_data` generation to prevent script crashes.
**How to avoid:** Remove `fallback_data` entirely. On execution or validation failure, write `{"doc_type": dt, "execution": {"status": "blocked", "error": str(exc)}}` to `research.json` and fail the validation check.
**Warning signs:** `execution.status` equal to `"fallback"` or research reports containing hardcoded template titles.

### Pitfall 2: Loose / Incomplete Schema Missing D-05 Fields
**What goes wrong:** Research output lacks `source_url`, `retrieval_date`, `supporting_excerpt`, `authority_classification`, or `remediation_hypothesis`.
**Why it happens:** Prompts or models only ask for basic title and description.
**How to avoid:** Define strict Pydantic model `FailureMode` enforcing every field required by D-05 and D-06, and reject LLM outputs that omit them.

### Pitfall 3: Cross-Pipeline Information Leakage (D-01, D-07, D-09 Violations)
**What goes wrong:** One document agent reads or modifies `crawler/eval/pipelines/<other_doc_type>/` or downstream worker prompts read research files.
**Why it happens:** Imperfect path parameters or hardcoded shared directories.
**How to avoid:** Construct paths strictly via `_PIPELINES_DIR / doc_type / "research" / "research.json"` and assert `path.resolve().is_relative_to(_PIPELINES_DIR / doc_type)`. Downstream workers in Phase 74 must receive only staged blind input folders.

### Pitfall 4: Subprocess Rate Limiting / Thread Thrashing
**What goes wrong:** Launching 23 simultaneous Copilot CLI processes causes CPU thrashing or CLI subprocess timeouts.
**Why it happens:** Unbounded concurrency (`asyncio.gather` on 23 items without a semaphore).
**How to avoid:** Cap `ThreadPoolExecutor(max_workers=4)`.

## Code Examples

### FailureMode and ResearchReport Schema Definition

```python
# Location: crawler/eval/doc_researcher.py
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class AuthorityClassification(str, Enum):
    AUTHORITATIVE = "authoritative"  # IRCC PDI, IRPR, Justice Laws, Court decisions
    DISCOVERY = "discovery"          # Forums, legal blogs, anecdotal, third-party

class FailureMode(BaseModel):
    failure_id: str = Field(..., description="Stable ID e.g. PASSPORT-FAIL-01")
    category: str = Field(..., description="Category e.g. validity_expiration")
    severity: str = Field("critical", description="critical or warning")
    title: str = Field(..., description="Short title of refusal trigger / PFL")
    description: str = Field(..., description="Detailed explanation")
    affected_fields: List[str] = Field(default_factory=list, description="Affected fields/evidence")
    authority_classification: AuthorityClassification = Field(
        ..., description="authoritative or discovery"
    )
    source_url: str = Field(..., description="Source URL or document citation")
    retrieval_date: str = Field(..., description="ISO retrieval date e.g. 2026-07-22")
    supporting_excerpt: str = Field(..., description="Exact supporting text span")
    remediation_hypothesis: str = Field(..., description="Guidance for applicant fix")
    local_corpus_verified: bool = Field(False, description="Verified against corpus/index.db")
    local_corpus_citations: List[str] = Field(default_factory=list, description="Corpus chunk IDs")

class ResearchReport(BaseModel):
    doc_type: str
    timestamp: str
    summary: str = Field(..., description="Human-readable executive summary")
    execution: dict = Field(..., description="Execution metadata status, model, duration")
    failure_modes: List[FailureMode] = Field(..., min_items=1)
```

### Copilot LLM Research Prompt Template

```python
def _build_research_prompt(doc_type: str, keywords: str, timestamp: str) -> str:
    return f"""You are a specialized Canadian Immigration Document Research Agent powered by Gemini 3.6 Flash long context.
Research real-world IRCC failure cases, refusal reasons, Procedural Fairness Letter (PFL) triggers, and critical applicant errors for Express Entry document type: '{doc_type}'.

Focus Keywords: {keywords}

Identify 3-5 specific real-world failure modes / PFL triggers for '{doc_type}'.
For each failure mode, distinguish whether it is based on official IRCC/Justice Laws policy ('authoritative') or third-party/forum/anecdotal discovery ('discovery').

Return ONLY a valid JSON object matching this structure:
{{
  "doc_type": "{doc_type}",
  "timestamp": "{timestamp}",
  "summary": "Human-readable summary of failure patterns for {doc_type}.",
  "failure_modes": [
    {{
      "failure_id": "{doc_type.upper()[:8]}-FAIL-01",
      "category": "category_key",
      "severity": "critical",
      "title": "Short title",
      "description": "Detailed description of refusal trigger / PFL",
      "affected_fields": ["field_name_1", "field_name_2"],
      "authority_classification": "authoritative",
      "source_url": "https://www.canada.ca/...",
      "retrieval_date": "{timestamp[:10]}",
      "supporting_excerpt": "Verbatim quote or exact excerpt from source",
      "remediation_hypothesis": "How applicant should remediate"
    }}
  ]
}}
"""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Unstructured serial LLM research scripts | Dedicated, schema-validated per-document research agents | Phase 72 (v12.0) | Eliminates generic fallbacks, enforces local corpus grounding, guarantees D-05/D-06 schema completeness, and isolates research per document type. |
| Hardcoded fallback JSON on failure | Fail-closed blocked status (`status: blocked`) | Phase 72 (v12.0) | Prevents synthetic fallback findings from masquerading as successful online research. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | All 23 Express Entry document types have at least 1-2 relevant policy chunks in `corpus/index.db`. | Local Corpus Grounding Gate | Some obscure document types may have zero local corpus hits, requiring failure modes to be classified as `discovery` evidence rather than `authoritative`. System correctly handles this via D-06. [CITED: skills/document-agents/_contract.md] |

## Open Questions (RESOLVED)

1. **RESOLVED: How should failure modes behave if local corpus search returns zero hits?**
   - Recommendation: As required by D-06, if local corpus verification fails or is absent, the failure mode must set `local_corpus_verified = False` and `authority_classification = "discovery"`. Unsupported policy claims must fail closed rather than being inferred as authoritative.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Copilot CLI | LLM Agent Execution (`gemini-3.6-flash`) | ✓ | PATH-resolved `copilot` | — |
| `corpus-crawler` CLI | Local FTS5 Corpus Verification | ✓ | `2.0.0` (`.venv/bin/python -m crawler.cli`) | — |
| Python Runtime | Test suite & Agent runner | ✓ | `3.10.12` (`.venv/bin/python`) | — |
| `pytest` | Conformance and Unit Testing | ✓ | `9.0.3` | — |

**Missing dependencies with no fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 |
| Config file | `pyproject.toml` |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py -x` |
| Full suite command | `.venv/bin/python -m pytest crawler/tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOC_RESEARCH-01 | Dedicated 23-agent research execution and schema validation | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py::test_research_schema_validation -x` | ❌ Wave 0 |
| DOC_RESEARCH-01 | No generic fallback research on failure (fail closed as blocked) | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py::test_blocked_pipeline_no_fallback -x` | ❌ Wave 0 |
| DOC_RESEARCH-01 | Local corpus verification gate & authority classification | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py::test_corpus_verification_gate -x` | ❌ Wave 0 |
| DOC_RESEARCH-01 | Cross-pipeline write isolation enforcement | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py::test_pipeline_isolation -x` | ❌ Wave 0 |
| DOC_RESEARCH-01 | All 23 ExpressEntryDocType research reports valid and non-blocked | conformance | `.venv/bin/python -m pytest crawler/tests/test_doc_research_conformance.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py`
- **Per wave merge:** `.venv/bin/python -m pytest crawler/tests/`
- **Phase gate:** All 23 research reports pass schema and isolation validation before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `crawler/tests/test_doc_researcher.py` — unit tests for schema validation, blocked pipeline semantics, corpus verification, and cross-pipeline isolation.
- [ ] `crawler/tests/test_doc_research_conformance.py` — conformance validator verifying all 23 pipeline research reports on disk.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Pipeline isolation (`crawler/eval/pipelines/<doc_type>/research/`) prevents cross-pipeline data contamination. |
| V5 Input Validation | yes | Pydantic / Dataclass schema validation for all LLM JSON outputs. |
| V8 Data Protection | yes | PII containment: personal data kept out of research manifests and downstream blind inputs. |

### Known Threat Patterns for Phase Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Information Leakage to Blind Workers | Information Disclosure | Staging blind inputs without research files or defect labels (D-07, D-09). |
| Ungrounded Policy Claims | Tampering / Misrepresentation | Local corpus verification gate (`corpus-crawler --json search`) and explicit `discovery` labeling (D-04, D-06). |
| Generic Fallback Masquerading as Success | Elevation of Privilege / Bypassing Gate | Fail closed as explicit `"status": "blocked"` on live call or validation failure (D-10). |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-CONTEXT.md` - Locked Decisions D-01..D-11. [VERIFIED: Local file]
- `skills/document-agents/_contract.md` - Grounding gate and `corpus-crawler --json search` envelope specification. [VERIFIED: Local file]
- `crawler/synthetic/schemas.py` - Canonical 23 `ExpressEntryDocType` values. [VERIFIED: Local file]
- `AGENTS.md` - System specification and fail-closed grounding directives. [VERIFIED: Local file]

### Secondary (MEDIUM confidence)
- Existing baseline `crawler/eval/doc_researcher.py`. [VERIFIED: Local file]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Built directly on established Copilot CLI, `corpus-crawler`, Pydantic, and pytest infrastructure.
- Architecture: HIGH - Strictly aligned with locked decisions D-01 through D-11.
- Pitfalls: HIGH - Derived directly from existing gaps in baseline `doc_researcher.py`.

**Research date:** 2026-07-22
**Valid until:** 2026-08-22
