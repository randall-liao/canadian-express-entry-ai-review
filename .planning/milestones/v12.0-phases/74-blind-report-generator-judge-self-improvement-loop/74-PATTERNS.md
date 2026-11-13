# Phase 74: Blind Report Generator & Judge Self-Improvement Loop - Pattern Map

**Mapped:** 2026-07-23  
**Files analyzed:** 10 new/refactored Phase 74 files + 11 legacy/existing files  
**Analogs found:** 10 / 10 (all files mapped to concrete existing codebase patterns or refactored targets)

---

## File Classification

| New / Refactored File | Role | Data Flow | Closest Analog | Match Quality |
|-----------------------|------|-----------|----------------|---------------|
| `crawler/eval/public_bundle.py` | utility / builder | transform | `skills/document-agents/_contract.md` & `crawler/grounding.py` | exact |
| `crawler/eval/pipeline_worker.py` | worker runner | request-response | `crawler/synthetic/staging.py` & `crawler/eval/real_worker.py` | exact (refactor target) |
| `crawler/eval/pipeline_judge.py` | judge runner | batched transform | `crawler/eval/real_judge.py` | exact (refactor target) |
| `crawler/eval/holdout_splitter.py` | utility / sealer | data transform | `crawler/eval/agent_improvement_loop.py` & `hashlib` | exact |
| `crawler/eval/genuine_optimizer.py` | optimizer agent | event-driven transform | `crawler/eval/real_worker.py` & `crawler/eval/genuine_optimizer.py` | exact (refactor target) |
| `crawler/eval/patch_evaluator.py` | service / gate | validation / gate | `crawler/eval/self_optimizer.py` | role-match |
| `crawler/eval/loop_orchestrator.py` | orchestrator | batch loop | `crawler/eval/agent_improvement_loop.py` | role-match |
| `crawler/tests/test_phase74_worker_isolation.py` | test | unit / contract | `crawler/synthetic/test_staging.py` | exact |
| `crawler/tests/test_phase74_judge_loop.py` | test | unit / contract | `crawler/tests/test_real_llm_engine.py` | exact |
| `crawler/tests/test_live_phase74_conformance_gate.py` | test | live gate | `crawler/tests/test_live_phase73_conformance_gate.py` | exact |

---

## Pattern Assignments

### 1. `crawler/eval/public_bundle.py` (utility / builder, transform)
**Purpose:** Build immutable, PII-free, research-free public review bundles per document type from `skills/document-agents/<doc_type>.md` and exact local corpus quotes (`corpus/index.db`), recording SHA-256 bundle hashes in Worker provenance.

**Analog:** `skills/document-agents/_contract.md` (lines 91-140) & `crawler/grounding.py` (lines 40-85)

**Public Bundle Assembly Pattern:**
```python
# Copy pattern from skills/document-agents/_contract.md & crawler/grounding.py
import hashlib
from pathlib import Path
from typing import Dict, Any

def build_public_review_bundle(doc_type: str, corpus_db_path: Path) -> Dict[str, Any]:
    """Assemble immutable public review bundle containing document skill rules and exact corpus quotes."""
    skill_file = Path("skills/document-agents") / f"{doc_type}.md"
    if not skill_file.is_file():
        raise FileNotFoundError(f"Missing public document skill: {skill_file}")
    
    skill_rules = skill_file.read_text(encoding="utf-8")
    # Public bundles must contain NO Phase 72 research, Phase 73 ground truth, or case labels
    bundle_content = f"# Public Review Rules: {doc_type}\n\n{skill_rules}"
    bundle_hash = hashlib.sha256(bundle_content.encode("utf-8")).hexdigest()
    
    return {
        "doc_type": doc_type,
        "content": bundle_content,
        "bundle_hash": bundle_hash,
    }
```

---

### 2. `crawler/eval/pipeline_worker.py` (worker runner, request-response)
**Purpose:** Execute independent Gemini 3.6 Flash long-context GitHub Copilot CLI Worker sessions over one staged opaque PDF attachment in an isolated temporary directory with zero repository access, `--no-custom-instructions`, and strict 5-field AnswerObject JSON extraction + grounding verification.

**Analog:** `crawler/synthetic/staging.py` (lines 61-125) & `crawler/eval/real_worker.py` (lines 161-220)

**Single-Case Attachment Isolation & Copilot Execution Pattern:**
```python
# Copy pattern from crawler/synthetic/staging.py & crawler/eval/real_worker.py
import subprocess
import json
from pathlib import Path
from crawler.synthetic.staging import stage_case_for_worker
from crawler.grounding import check_answer_grounding

def run_blind_worker_task(opaque_case_id: str, doc_type: str, public_bundle: Dict[str, Any]) -> Dict[str, Any]:
    # 1. Stage single opaque PDF into isolated temporary workspace (outside pipeline root)
    staged_pdf = stage_case_for_worker(opaque_case_id)
    staging_cwd = staged_pdf.parent  # FRESH CWD, NOT REPO ROOT

    prompt = f"""You are the live LLM Worker for a blind Canadian Express Entry document review.
Document type: {doc_type}
Opaque case ID: {opaque_case_id}

PUBLIC REVIEW BUNDLE (Hash: {public_bundle['bundle_hash']}):
{public_bundle['content']}

Evaluate ONLY the attached PDF in your working directory.
Return ONLY one valid JSON AnswerObject with fields: question, claims, basis, abstentions, prose."""

    # 2. Invoke Copilot CLI in staging CWD with NO repo cwd, NO tools, NO custom instructions
    cmd = [
        "copilot", "-p", prompt,
        "--model", "gemini-3.6-flash",
        "-s", "--no-custom-instructions"
    ]
    
    res = subprocess.run(cmd, cwd=str(staging_cwd), capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        _record_worker_failure(opaque_case_id, res.stderr)
        raise RuntimeError(f"Worker process failed for {opaque_case_id}")

    # 3. Parse AnswerObject JSON and verify local grounding gate
    answer = _extract_json_object(res.stdout, {"question", "claims", "basis", "abstentions", "prose"})
    check_answer_grounding(answer)
    answer["_provenance"] = {
        "engine": "copilot-cli",
        "model": "gemini-3.6-flash",
        "bundle_hash": public_bundle['bundle_hash'],
        "staging_dir": str(staging_cwd),
        "is_live": True,
    }
    return answer
```

---

### 3. `crawler/eval/pipeline_judge.py` (judge runner, batched transform)
**Purpose:** Run exactly one privileged GitHub Copilot CLI session per document type per evaluation pass using `claude-opus-4.8` with `--effort xhigh` and `--context long_context`, batching all 10 or 12 Worker reports and PDF attachments alongside Phase 72 research and Phase 73 ground truth specs.

**Analog:** `crawler/eval/real_judge.py` (lines 116-192)

**Batched Claude Opus 4.8 xhigh Long-Context Judge Pattern:**
```python
# Copy pattern from crawler/eval/real_judge.py
from pydantic import BaseModel, Field
from typing import Dict, List, Any

class CaseScore(BaseModel):
    grounding_accuracy: float = Field(ge=0.0, le=1.0)
    citation_exactness: float = Field(ge=0.0, le=1.0)
    defect_recall: float = Field(ge=0.0, le=1.0)
    pii_containment: float = Field(ge=0.0, le=1.0)
    blind_input_compliance: float = Field(ge=0.0, le=1.0)

class JudgeEvaluationBatch(BaseModel):
    doc_type: str
    case_evaluations: Dict[str, CaseScore]
    findings: List[Dict[str, str]]
    patch_recommendations: List[Dict[str, str]]
    rationale: str

def run_batched_document_judge(
    doc_type: str,
    worker_reports: Dict[str, Dict[str, Any]],
    pdf_paths: List[Path],
    research_json: Dict[str, Any],
    ground_truth_specs: Dict[str, Dict[str, Any]],
) -> JudgeEvaluationBatch:
    prompt = f"""You are the privileged LLM Judge for document review evaluation.
Model: claude-opus-4.8 (--effort xhigh, --context long_context)
Document Type: {doc_type}

Evaluate all Worker reports against attached PDFs, research, and ground truth specs.
WORKER REPORTS: {json.dumps(worker_reports)}
RESEARCH: {json.dumps(research_json)}
GROUND TRUTH: {json.dumps(ground_truth_specs)}

Return ONLY a valid JSON object matching JudgeEvaluationBatch schema."""

    cmd = [
        "copilot", "-p", prompt,
        "--model", "claude-opus-4.8",
        "--effort", "xhigh",
        "--context", "long_context",
        "-s", "--no-custom-instructions"
    ]
    # Attach all 10 or 12 PDFs in batch call
    for pdf in pdf_paths:
        cmd.extend(["--attach", str(pdf)])

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if res.returncode != 0:
        raise RuntimeError(f"Batched Judge execution failed for {doc_type}: {res.stderr}")
    
    raw = json.loads(res.stdout.strip())
    # Fail closed on schema invalidity - ZERO deterministic score fallback
    return JudgeEvaluationBatch.model_validate(raw)
```

---

### 4. `crawler/eval/holdout_splitter.py` (utility / sealer, data transform)
**Purpose:** Group cases by logical sibling pairs and partition into training and sealed holdout sets before optimization passes. Holdout valid control pair plus one deterministically hashed defective pair remain strictly sealed from optimizer agents.

**Analog:** `crawler/eval/agent_improvement_loop.py` (lines 43-72) & `hashlib`

**Logical Sibling Group Train/Holdout Sealing Pattern:**
```python
# Copy pattern from crawler/eval/agent_improvement_loop.py
import hashlib
from typing import List, Dict, Any, Tuple

def split_sibling_groups(doc_type: str, logical_cases: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split cases into training and sealed holdout sets by sibling group."""
    valid_controls = [c for c in logical_cases if c.get("expected_verdict") == "meets_requirements"]
    defective_cases = [c for c in logical_cases if c.get("expected_verdict") != "meets_requirements"]

    # Holdout gets the 1 valid control pair
    holdout_valid = valid_controls[:1]
    train_valid = valid_controls[1:]

    # Select 1 defective pair deterministically using hash
    hash_val = int(hashlib.sha256(doc_type.encode()).hexdigest(), 16)
    selected_idx = hash_val % len(defective_cases)
    
    holdout_defective = [defective_cases[selected_idx]]
    train_defective = [c for i, c in enumerate(defective_cases) if i != selected_idx]

    holdout_set = holdout_valid + holdout_defective
    train_set = train_valid + train_defective
    return train_set, holdout_set
```

---

### 5. `crawler/eval/genuine_optimizer.py` (optimizer agent, event-driven transform)
**Purpose:** Drive real Gemini 3.6 Flash long-context optimizer agents to propose skill/prompt patches into candidate proposal directories (`proposals/candidate_<hash>/`) based exclusively on training Judge findings.

**Analog:** `crawler/eval/real_worker.py` (lines 161-205) & `crawler/eval/genuine_optimizer.py` (refactor target)

**Sandboxed Real Optimizer Candidate Proposal Pattern:**
```python
# Copy pattern from crawler/eval/real_worker.py
def run_candidate_optimization_pass(doc_type: str, train_judge_findings: List[Dict[str, Any]], proposal_dir: Path) -> Path:
    """Drive Gemini optimizer agent to generate a candidate patch in proposal sandbox."""
    prompt = f"""You are the Gemini 3.6 Flash Optimizer agent for document type '{doc_type}'.
Analyze the following TRAINING Judge findings (holdout cases are sealed):
{json.dumps(train_judge_findings, indent=2)}

Propose targeted improvements to skills/document-agents/{doc_type}.md.
Output a valid candidate patch proposal JSON with fields: target_file, proposed_diff, rationale."""

    cmd = [
        "copilot", "-p", prompt,
        "--model", "gemini-3.6-flash",
        "-s", "--no-custom-instructions"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        raise RuntimeError(f"Optimizer failed for {doc_type}")

    proposal_dir.mkdir(parents=True, exist_ok=True)
    candidate_file = proposal_dir / f"candidate_{doc_type}.json"
    candidate_file.write_text(res.stdout, encoding="utf-8")
    return candidate_file
```

---

### 6. `crawler/eval/patch_evaluator.py` (service / gate, validation / gate)
**Purpose:** Scan candidate patches against allowlist safety rules (reject fixture labels, case IDs, synthetic applicant facts, or ungrounded rules) and evaluate candidate review bundles in memory. Accept and commit atomically ONLY if targeted training metrics improve AND zero holdout dimension regresses.

**Analog:** `crawler/eval/self_optimizer.py` (lines 190-250)

**Allowlist Scanner & Non-Regressing Acceptance Gate Pattern:**
```python
# Copy pattern from crawler/eval/self_optimizer.py
import re

ALLOWLIST_FORBIDDEN_PATTERNS = [
    re.compile(r"\bcase_\d{3}\b", re.IGNORECASE),
    re.compile(r"\bground_truth\b", re.IGNORECASE),
    re.compile(r"\bJane Synthetic\b", re.IGNORECASE),
    re.compile(r"\bJohn Synthetic\b", re.IGNORECASE),
]

def validate_patch_allowlist(patch_content: str) -> bool:
    for pattern in ALLOWLIST_FORBIDDEN_PATTERNS:
        if pattern.search(patch_content):
            return False
    return True

def should_accept_candidate(
    baseline_train: Dict[str, float],
    baseline_holdout: Dict[str, float],
    candidate_train: Dict[str, float],
    candidate_holdout: Dict[str, float],
) -> bool:
    """Accept IF AND ONLY IF train score improves AND zero holdout dimension regresses."""
    train_improved = candidate_train["overall"] > baseline_train["overall"]
    
    holdout_regressed = any(
        candidate_holdout[m] < baseline_holdout[m]
        for m in ("grounding_accuracy", "citation_exactness", "defect_recall", "pii_containment", "blind_input_compliance")
    )
    return train_improved and not holdout_regressed
```

---

### 7. `crawler/eval/loop_orchestrator.py` (orchestrator, batch loop)
**Purpose:** Drive baseline, up to 3 optimization iterations (targeting failed training cases + full holdout re-evaluation), and final full pass across all 236 cases, maintaining structured iteration artifact layout `pipelines/<doc_type>/iterations/iter_<N>/`.

**Analog:** `crawler/eval/agent_improvement_loop.py` (lines 214-260)

**Iteration Artifact Layout Pattern:**
```
crawler/eval/pipelines/<doc_type>/iterations/
├── iter_00_baseline/
│   ├── worker_reports/
│   └── judge_eval/
├── iter_01/
│   ├── worker_reports/
│   ├── judge_eval/
│   └── proposals/
└── iter_final/
    ├── worker_reports/
    └── judge_eval/
```

---

### 8. `crawler/tests/test_phase74_worker_isolation.py` (test, unit / contract)
**Purpose:** Verify Worker attachment staging, fresh temporary directory containment, non-repo CWD, AnswerObject grounding, public bundle hashing, and fail-closed blindness enforcement using injected non-live runners.

**Analog:** `crawler/synthetic/test_staging.py`

---

### 9. `crawler/tests/test_phase74_judge_loop.py` (test, unit / contract)
**Purpose:** Verify batched Opus 4.8 Judge schema validation, model/effort flags, 100% case coverage assertions, sibling group holdout sealing, optimizer sandbox isolation, and candidate patch acceptance/rejection rules.

**Analog:** `crawler/tests/test_real_llm_engine.py`

---

### 10. `crawler/tests/test_live_phase74_conformance_gate.py` (test, live gate)
**Purpose:** Non-seeding live conformance gate requiring `REQUIRE_LIVE_PHASE74_CONFORMANCE=1`, verifying genuine Copilot execution provenance (`engine: copilot-cli`, `is_live: true`), 236 Worker reports, 23 batched Judge sessions, sealed holdout evidence, and patch audit trails.

**Analog:** `crawler/tests/test_live_phase73_conformance_gate.py`

---

## Shared Patterns

### Shared Pattern 1: Grounding & AnswerObject Schema Gate
**Source:** `skills/document-agents/_contract.md` (lines 62-80) & `crawler/grounding.py`  
**Apply to:** All Worker review outputs across all 23 document types.  
```python
# Shared AnswerObject structure enforced across all workers
{
    "question": str,
    "claims": [{"id": str, "text": str, "citations": [str], "quote": str}],
    "basis": [str],  # PII partition
    "abstentions": [{"text": str, "reason": str}],
    "prose": str
}
```

### Shared Pattern 2: Pydantic Schema Validation & Fail-Closed Errors
**Source:** `crawler/eval/real_judge.py` & `crawler/eval/real_worker.py`  
**Apply to:** All Worker, Judge, and Optimizer response parsing.  
```python
# Fail-closed Pydantic schema validation without deterministic score fallback
try:
    data = json.loads(stdout)
    validated = ModelSchema.model_validate(data)
except Exception as exc:
    _record_execution_failure(case_id, exc)
    raise RuntimeError(f"Schema validation failed: {exc}")
```

---

## Flagged Legacy Anti-Patterns

| Anti-Pattern | Where Found | Why Forbidden in Phase 74 | Phase 74 Corrective Pattern |
|--------------|-------------|--------------------------|-----------------------------|
| **Repository CWD for Workers** | `pipeline_worker.py` line 97, `real_worker.py` line 189 | Allows Worker CLI agents to access privileged research, ground truth, or source code via file tools. | Execute Worker CLI strictly inside fresh temporary staging directory (`stage_case_for_worker`) outside pipeline root. |
| **`--allow-all` Flag on Blind Workers** | `pipeline_worker.py` line 88, `real_worker.py` line 181 | Grants write, web, shell, and filesystem privileges to blind report generators. | Remove `--allow-all` and pass `--no-custom-instructions` with zero tool permissions. |
| **Hardcoded Binary Executable Paths** | `pipeline_worker.py` line 27, `pipeline_judge.py` line 26 | Breached portability with a machine-specific Linuxbrew path. | Use portable executable discovery (`shutil.which("copilot")` or `copilot` on PATH). |
| **Plain-Text & Regex LLM Parsing** | `real_worker.py` lines 46-77, `real_judge.py` lines 18-23 | Fragile stdout parsing subject to truncation, ANSI escapes, and hallucinated fences. | Strict JSONL event filtering (`assistant.message`) and Pydantic schema validation (`model_validate`). |
| **Deterministic Score Fallback** | `pipeline_judge.py` lines 156-216 | Generates fake heuristic scores/findings when Judge Copilot call fails or times out. | Fail closed on Judge CLI failure; record `judge_error.json` and block the pipeline. Never fabricate scores in Python. |
| **Ground-Truth-Derived Worker Reports** | `pipeline_worker.py` lines 119-143, `agent_improvement_loop.py` lines 88-138 | Synthesizes Worker AnswerObjects from ground truth JSON instead of running real LLM agent sessions. | Execute real Gemini 3.6 Flash long-context Copilot sessions for every blind test case. |
| **Canned Append Patches** | `genuine_optimizer.py` lines 92-127 | Appends hardcoded static text strings to `AGENTS.md` and `skills/pdf/SKILL.md`. | Replace with real Gemini agent proposal passes writing diffs to proposal sandbox directories. |
| **Optimizer Access to Holdout Data** | `self_optimizer.py` lines 80-140 | Feeds holdout case failures and ground truth to optimizer agents, causing overfit. | Seal holdout Judge findings, ground truth specs, and rationales strictly from optimizer agent inputs. |
| **Cached-Output Acceptance Without Hashes** | `real_judge.py` lines 121-131 | Accepts cached worker outputs without verifying SHA-256 prompt/bundle hashes or live provenance. | Invalidate caches unless SHA-256 bundle hashes match and live Copilot provenance is verified. |
| **Direct Concurrent Source Edits** | `genuine_optimizer.py` lines 75-90 | Optimizers write proposed patches directly to shared source files (`AGENTS.md`, `skills/`). | Write candidate patches to isolated sandbox directories (`proposals/candidate_<hash>/`) and evaluate before atomic commit. |

---

## No Analog Found

| File | Role | Data Flow | Reason / Resolution |
|------|------|-----------|---------------------|
| *None* | N/A | N/A | Every Phase 74 capability maps directly to a concrete existing asset or refactoring target in `crawler/eval/` and `crawler/synthetic/`. |

---

## Metadata

**Analog search scope:** `crawler/eval/`, `crawler/synthetic/`, `skills/document-agents/`, `skills/pdf/`, `AGENTS.md`  
**Files scanned:** 21 files  
**Pattern extraction date:** 2026-07-23  
