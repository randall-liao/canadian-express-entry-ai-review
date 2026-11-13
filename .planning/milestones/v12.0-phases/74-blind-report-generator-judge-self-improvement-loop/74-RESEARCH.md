# Phase 74: Blind Report Generator & Judge Self-Improvement Loop - Research

**Researched:** 2026-07-23  
**Domain:** Blind LLM Agent Execution, Privileged Evaluation, Holdout Sealing, Self-Improvement Prompt/Skill Patching  
**Confidence:** HIGH  

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Execute exactly one independent Gemini 3.6 Flash long-context GitHub Copilot CLI Worker session for each of the 236 opaque PDF fixtures.
- **D-02:** A Worker receives only: one Phase 73 staged opaque PDF attachment, allowed extracted text, the normal document upload-slot type, and a public review evidence bundle assembled from canonical document skills plus authoritative local corpus chunks. It receives no research report, GenerationSpec, ground truth, sibling mapping, failure ID, expected verdict, variant label, or privileged path.
- **D-03:** Workers run from the fresh Phase 73 staging directory with `--no-custom-instructions`, no unrestricted path permission, no repository cwd, and no shell/write/GitHub/web capability. All review evidence is inline or attached.
- **D-04:** Worker output is a strict five-field AnswerObject plus truthful execution provenance. It is captured from canonical JSONL final-message events only, passed through the local grounding gate, and fails closed on process, schema, citation, quote, PII, or blindness errors.
- **D-05:** Native and scanned siblings run in separate sessions and cannot share session history, cached outputs, filenames, or case mappings.
- **D-06:** Build one immutable public review bundle per document type from `skills/document-agents/` and exact corpus citations/quotes. Bundles may describe normal requirements but contain no Phase 72 failure research, Phase 73 defect selection, case labels, or Judge-only information.
- **D-07:** Bundle hashes are recorded in Worker provenance so each report can be reproduced and compared across iterations without revealing privileged inputs.
- **D-08:** Run exactly one privileged Judge session per document type per evaluation pass, batching that type's Worker reports and 10 or 12 PDF attachments. The Judge alone receives Phase 72 research, Phase 73 private ground truth/sibling mapping, Worker reports, and authoritative evidence.
- **D-09:** Every Judge session uses GitHub Copilot CLI model `claude-opus-4.8`, `--effort xhigh`, and `--context long_context`. No GPT or deterministic evaluator may be reported as the Judge.
- **D-10:** Judge outputs strict per-case scores for grounding accuracy, citation exactness, defect recall, PII containment, and blind-input compliance, plus evidence-based findings and training-only patch recommendations. Process or schema failure is blocked; deterministic score fallback is prohibited.
- **D-11:** Python may validate Judge structure, recompute deterministic counts/hashes, and aggregate metrics, but may not generate semantic scores or missed-defect findings from ground truth.
- **D-12:** Split by logical sibling group, never individual PDF, before optimization. For each document type, hold out the valid-control sibling pair plus one deterministic hashed defective sibling pair; all remaining pairs are training.
- **D-13:** Optimizer agents receive only training Judge findings. Holdout ground truth, Judge rationales, scores, and failure labels remain sealed until candidate evaluation completes.
- **D-14:** Baseline and final evaluation cover all 236 cases. Each optimization iteration reruns failed training cases plus all holdout cases; a final full pass confirms global metrics.
- **D-15:** Run one Gemini 3.6 Flash long-context optimizer agent per document type to propose changes only to that document type's skill. A separate Gemini optimizer may propose shared `AGENTS.md` / `skills/pdf/SKILL.md` changes from aggregated training findings.
- **D-16:** Optimizers write candidate files/diffs only inside isolated proposal directories. They never edit shared source directly and never read another document type's ground truth.
- **D-17:** Candidate review bundles are evaluated without modifying source. Apply a candidate only when targeted training metrics improve and no holdout dimension regresses. Rejected candidates leave source unchanged and retain evidence.
- **D-18:** Accepted patches are allowlisted, bounded, publish-safe, grounding-safe, and committed atomically. No patch may add literal fixture labels, case IDs, ground-truth paths, synthetic applicant values, ungrounded immigration rules, or weaken PII/abstention contracts.
- **D-19:** Run at most three iterations and stop on perfect scores, no actionable training failures, no accepted non-regressing patch, provider quota blocker, or convergence. A perfect baseline requires no artificial patch.
- **D-20:** Store Worker/Judge/optimizer artifacts beneath each document pipeline and iteration, but never stage those directories to Workers. Shared aggregate reports contain no synthetic applicant facts.
- **D-21:** Ordinary tests use injected non-live runners and temporary roots. Explicit live gates never seed outputs and reject injected, cached-without-hash, deterministic, missing, partial, or stale artifacts.
- **D-22:** Phase completion requires truthful live provenance for all executed roles, complete baseline/final metrics, sealed-holdout evidence, accepted/rejected patch audit trails, no grounding/PII/blindness regression, and no unresolved high-severity Judge finding.

### the agent's Discretion
- Bounded concurrency, exact JSON schema names, and iteration targeting are implementation details, provided all privilege, holdout, real-agent, and acceptance gates remain enforceable.

### Deferred Ideas (OUT OF SCOPE)
- GPT 5.6 SOL XHIGH cross-phase orchestration, final release gate handling, and root `TEST_REPORT.md` export — Phase 75.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| `ISOLATED_PIPELINE-01` | Run each document type in `crawler/eval/pipelines/<doc_type>/` and stage report-generator inputs so workers can access only the blind PDF and allowed extracted text, never research, ground truth, defect labels, revealing filenames, or privileged paths. | Section 1 & Section 4 document the exact Copilot CLI execution in isolated CWDs, filesystem staging, and side-channel elimination. |
| `JUDGE_IMPROVE-01` | Allow only a GitHub Copilot CLI Judge using Claude Opus 4.8 with `xhigh` reasoning and `long_context` to compare blind worker reports with research and ground truth, score defect recall, grounding, citation exactness, and PII containment, then drive measured prompt/skill improvements. | Section 2 & Section 5 document the batched per-document Judge execution, schema validation, logical train/holdout split, and sandboxed candidate patching loop. |
| `REAL_AGENT_EXECUTION-01` | Execute every claimed researcher, synthetic generator, report worker, Judge, optimizer, and orchestrator role through a real GitHub Copilot CLI agent session with the assigned model/context/effort; production failures must be explicit and no deterministic or hardcoded substitute may be reported as model output. | Section 3, Section 6 & Section 9 document exact Copilot CLI commands, model assignments, JSONL event parsing, truthful provenance, and elimination of fake/fallback paths. |
</phase_requirements>

## Summary

Phase 74 implements the complete blind evaluation and genuine self-improvement loop across all 23 Express Entry document types and 236 blind PDF fixtures generated in Phase 73. Each report-generating Worker runs as an isolated, real GitHub Copilot CLI session using `gemini-3.6-flash` long context over a single staged PDF attachment in a fresh temporary workspace. Workers are granted zero repository cwd access, no custom instructions, and no tool or write privileges, receiving only the staged opaque PDF and a public review evidence bundle assembled from canonical document skills (`skills/document-agents/`) and exact local corpus chunks (`corpus/index.db`).

The evaluation tier is strictly privileged: exactly one batched GitHub Copilot CLI Judge session runs per document type using `claude-opus-4.8` with `--effort xhigh` and `--context long_context`. The Judge evaluates all 10 or 12 cases for that document type simultaneously, receiving the Worker AnswerObject reports, the PDF attachments, Phase 72 failure research, and Phase 73 private ground-truth manifests. Python validates the Judge JSON output structure and aggregates metrics, but is strictly prohibited from generating semantic scores, inventing missed defects, or substituting deterministic fallback evaluation.

Self-improvement is strictly controlled through logical sibling-group train/holdout splits. For each document type, the valid control pair plus one deterministically hashed defective pair are sealed into a holdout set, leaving the remaining pairs for training. Per-document Gemini optimizers and one shared optimizer propose prompt and skill guidance patches into isolated candidate directories. Candidate review bundles are tested in memory without editing source files; a patch is accepted and committed atomically ONLY if targeted training metrics improve AND zero holdout dimension regresses across at most three iterations.

## Primary Recommendation

Implement a modular, schema-enforced pipeline engine in `crawler/eval/` that completely replaces legacy fake/fallback paths (`pipeline_worker.py`, `pipeline_judge.py`, `real_worker.py`, `real_judge.py`, `genuine_optimizer.py`, `agent_improvement_loop.py`, `benchmark_runner.py`, `self_optimizer.py`). Drive all Worker, Judge, and Optimizer roles through truthful GitHub Copilot CLI invocations with explicit live provenance (`engine: copilot-cli`, `is_live: true`), isolated staging workspaces via `stage_case_for_worker`, strict Pydantic JSON schema validation, sealed holdouts, and zero deterministic semantic fallbacks.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| **Blind Fixture Staging** | Local Staging API (`crawler/synthetic/staging.py`) | OS Filesystem (`tempfile`) | Isolate individual opaque PDF attachments outside the privileged pipeline tree with strict permission and containment checks. |
| **Public Evidence Construction** | Public Review Bundle Builder (`crawler/eval/public_bundle.py`) | Search Index (`corpus/index.db`) | Assemble immutable, PII-free, research-free review rules and exact corpus quotes per document type with SHA-256 provenance tracking. |
| **Blind Report Workers** | Live Copilot CLI (`gemini-3.6-flash` long_context) | Local Grounding Gate (`crawler/grounding.py`) | Execute independent review sessions with zero repo cwd or tool privileges, emitting 5-field AnswerObjects verified by the local grounding gate. |
| **Privileged Evaluation** | Live Copilot CLI (`claude-opus-4.8` xhigh long_context) | Python Schema Validator | Perform batched per-document evaluation across Worker reports, PDFs, research, and ground truth; Python validates structure and aggregates metrics without fabricating scores. |
| **Train/Holdout Sealing** | Sibling Group Splitter (`crawler/eval/holdout_splitter.py`) | Hash Engine (`hashlib`) | Partition 118 logical sibling pairs into training and sealed holdouts before optimization, sealing holdout findings from optimizer agents. |
| **Candidate Optimization** | Live Copilot CLI (`gemini-3.6-flash` long_context) | Proposal Sandbox | Generate isolated skill and prompt patch proposals in candidate directories without direct source edits or cross-document contamination. |
| **Patch Acceptance Gate** | Regression Gate (`crawler/eval/patch_evaluator.py`) | Git Atomic Commit Engine | Evaluate candidate patches against train improvement and zero holdout regression before atomic commit to repository source files. |

## Standard Stack

### Core
| Library / Tool | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| **GitHub Copilot CLI** | `1.0.73` [VERIFIED: CLI `copilot --version`] | Agent Execution Runtime | Executable CLI engine driving real `gemini-3.6-flash` and `claude-opus-4.8` sessions via `-p` prompts and JSONL event parsing. |
| **Python** | `>=3.10,<4.0` [VERIFIED: `pyproject.toml`] | Orchestration & Validation | Standard runtime environment for Pydantic validation, subprocess execution, and test automation. |
| **Pydantic** | `>=2.13,<3.0` [VERIFIED: `pyproject.toml`] | Schema Validation | Hardened JSON schema validation for AnswerObjects, Judge evaluations, and patch candidate metadata. |
| **pdfminer.six** | `>=20260107,<20270000` [VERIFIED: `pyproject.toml`] | PDF Text Extraction | Pure-Python PDF text layer extraction for allowed Worker text and Judge text verification. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pypdfium2** | `>=5.11,<6.0` [VERIFIED: `pyproject.toml`] | High-DPI PDF Rendering | PDF page rendering for visual inspection and scan rasterization verification. |
| **Pillow** | `>=12.3,<13.0` [VERIFIED: `pyproject.toml`] | Image Processing | Image byte manipulation and scan artifact analysis. |
| **pytest** | `>=9.0.3` [VERIFIED: `.venv`] | Automated Test Suite | Unit, contract, and live gate conformance testing with `REQUIRE_LIVE_PHASE74_CONFORMANCE`. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| **Copilot CLI Claude Opus 4.8 xhigh** | OpenAI GPT-4o / Local LLM | Violates D-09 requirement specifying Claude Opus 4.8 xhigh long context for the privileged Judge. |
| **Copilot CLI Gemini 3.6 Flash** | Direct REST API calls | Violates `REAL_AGENT_EXECUTION-01` requirement specifying GitHub Copilot CLI agent sessions. |
| **Logical Sibling-Group Split** | Individual PDF Random Split | Sibling leakage: splitting native and scanned variants of the same logical case across train and holdout leaks injected defect structure. |
| **Isolated Proposal Sandbox** | Direct File Edits | Unsafe concurrent edits to `AGENTS.md` and `skills/` corrupt source state on rejected or failing patch candidates. |

### Package Legitimacy Audit

> All required packages are pre-installed in the repository virtual environment (`.venv`) and frozen in `pyproject.toml`. No new external packages are installed in Phase 74.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `pydantic` | PyPI | 8 yrs | 50M/wk | github.com/pydantic/pydantic | [OK] | Pre-installed |
| `pdfminer.six` | PyPI | 10 yrs | 5M/wk | github.com/pdfminer/pdfminer.six | [OK] | Pre-installed |
| `pypdfium2` | PyPI | 4 yrs | 200k/wk | github.com/pypdfium2-team/pypdfium2 | [OK] | Pre-installed |
| `Pillow` | PyPI | 14 yrs | 80M/wk | github.com/python-pillow/Pillow | [OK] | Pre-installed |

**Packages removed due to [SLOP] verdict:** None  
**Packages flagged as suspicious [SUS]:** None  

## Architecture Patterns

### System Architecture Diagram

```
                       +-------------------------------------------------------+
                       |           Phase 73 Opaque PDF Fixtures (236)         |
                       |       (118 Native Vector + 118 Scanned Siblings)      |
                       +-------------------------------------------------------+
                                                   |
                                                   v
                       +-------------------------------------------------------+
                       |              Stage Case for Worker (D-03)             |
                       |     Isolated CWD: /tmp/stage_<hash>/<opaque_id>.pdf   |
                       |    (No repo cwd, no custom instructions, no tools)    |
                       +-------------------------------------------------------+
                                                   |
                                                   v
                       +-------------------------------------------------------+
                       |           Gemini 3.6 Flash Blind Worker (D-01)        |
                       |          Receives: PDF + Public Evidence Bundle       |
                       |       Outputs: 5-Field AnswerObject JSONL Event       |
                       +-------------------------------------------------------+
                                                   |
                                                   v
                       +-------------------------------------------------------+
                       |              Local Grounding Gate Check               |
                       |          Confirms claims, quotes, and PII             |
                       +-------------------------------------------------------+
                                                   |
                                                   v
                       +-------------------------------------------------------+
                       |    Privileged Batched Claude Opus 4.8 Judge (D-08)     |
                       | Batch per DocType (10 or 12 PDFs + Worker Reports +   |
                       |   Phase 72 Research + Phase 73 Ground Truth Specs)   |
                       |      Outputs: Per-case Scores + Training Findings    |
                       +-------------------------------------------------------+
                                                   |
                                           +-------+-------+
                                           |               |
                                           v               v
                             +-------------------+   +--------------------+
                             |  Train Findings   |   | Sealed Holdouts    |
                             | (Passed to Opts)  |   | (Sealed from Opts) |
                             +-------------------+   +--------------------+
                                       |                       |
                                       v                       |
                             +-------------------+             |
                             | Per-Doc & Shared  |             |
                             | Gemini Optimizers |             |
                             | Writes Proposals  |             |
                             +-------------------+             |
                                       |                       |
                                       +-------+-------+-------+
                                               |
                                               v
                             +-----------------------------------+
                             |     Patch Acceptance Evaluator     |
                             |  Train Delta > 0 AND Holdout == 0 |
                             +-----------------------------------+
                                               |
                                               v
                             +-----------------------------------+
                             |  Atomic Commit to Source File     |
                             +-----------------------------------+
```

### Recommended Project Structure
```
crawler/
└── eval/
    ├── pipeline_worker.py       # Refactored: Live Gemini 3.6 Flash Worker runner (D-01..D-05)
    ├── pipeline_judge.py        # Refactored: Batched per-doc Opus 4.8 Judge harness (D-08..D-11)
    ├── public_bundle.py         # New: Immutable public review bundle builder (D-06, D-07)
    ├── holdout_splitter.py      # New: Logical sibling-group train/holdout splitter & sealer (D-12, D-13)
    ├── genuine_optimizer.py     # Refactored: Real Gemini candidate patch optimizer (D-15..D-18)
    ├── patch_evaluator.py       # New: Candidate patch overlay evaluator & holdout regression gate
    ├── loop_orchestrator.py     # New: Iteration loop driver (max 3 iterations, targeted reruns) (D-14, D-19)
    └── pipelines/               # Per-document pipeline tree (23 doc types)
        └── <doc_type>/
            ├── research/        # Privileged Phase 72 research.json & research_summary.md
            ├── ground_truth/    # Privileged Phase 73 private ground truth specs (*.json)
            ├── test_data/       # Privileged Phase 73 vector and scanned PDF fixtures (*.pdf)
            └── iterations/      # Phase 74 iteration state & artifacts (D-20)
                ├── iter_00_baseline/
                │   ├── worker_reports/
                │   └── judge_eval/
                ├── iter_01/
                │   ├── worker_reports/
                │   ├── judge_eval/
                │   └── proposals/
                └── iter_final/
```

### Pattern 1: Blind Worker Execution with Copilot CLI
**What:** Execute one independent Gemini 3.6 Flash long-context GitHub Copilot CLI session for a staged PDF fixture in a fresh, isolated workspace.  
**When to use:** Every blind report generation pass across the 236 opaque PDF test fixtures.  
**Implementation Guidelines:**
1. Call `stage_case_for_worker(opaque_case_id, target_dir)` to construct a fresh staging directory outside the pipeline tree containing ONLY `<opaque_id>.pdf` (and optional `<opaque_id>.txt`).
2. Construct prompt containing the public review evidence bundle (`skills/document-agents/<doc_type>.md` plus exact corpus quotes) and the document upload-slot name.
3. Spawn Copilot CLI in the staging directory with command arguments:
   `copilot -p "<prompt>" --model gemini-3.6-flash -s --no-custom-instructions`
   *(Do NOT pass `--allow-all`, `--available-tools`, or set cwd to repository root).*
4. Capture JSONL stream, filter for `assistant.message` events, extract the 5-field AnswerObject JSON, and run `check_answer_grounding` via `crawler.grounding`.
5. Fail closed on subprocess failure, JSON decode error, schema invalidity, ungrounded claim, or PII leak by removing any stale `<case_id>.json` and persisting `<case_id>.error.json`.

### Pattern 2: Privileged Batched Judge Evaluation Harness
**What:** Run exactly one privileged GitHub Copilot CLI session per document type per evaluation pass, batching that document type's 10 or 12 Worker reports and PDF attachments.  
**When to use:** Every evaluation pass (baseline, iteration reruns, and final full pass).  
**Implementation Guidelines:**
1. Collect all 10 or 12 cases for the target document type (5 or 6 logical cases x 2 variants).
2. Prepare privileged Judge prompt containing:
   - Worker AnswerObject review reports for all cases.
   - Privileged Phase 72 research manifest (`research.json`).
   - Privileged Phase 73 private ground-truth specs (`ground_truth/*.json`).
   - Public review evidence bundle.
3. Invoke Copilot CLI with model `claude-opus-4.8`, effort `xhigh`, long context, and PDF attachments:
   `copilot -p "<prompt>" --model claude-opus-4.8 --effort xhigh --context long_context -s --no-custom-instructions`
4. Parse JSON output and validate against `JudgeEvaluationBatch` schema. Python recomputes aggregate metrics (`grounding_accuracy`, `citation_exactness`, `defect_recall`, `pii_containment`, `blind_input_compliance`) and confirms 100% case coverage without overriding LLM semantic scores.

### Pattern 3: Isolated Sibling-Group Train/Holdout Split & Sealing
**What:** Split logical cases into training and sealed holdout sets by sibling group before optimization.  
**When to use:** Prior to running self-improvement optimization loops.  
**Implementation Guidelines:**
1. Group the 118 logical cases by document type (5 cases for 20 types; 6 cases for 3 types).
2. For each document type, select the valid control sibling pair (1 vector + 1 scanned) and ONE defective sibling pair deterministically using `int(hashlib.sha256(doc_type.encode()).hexdigest(), 16) % len(defective_pairs)`.
3. Seal holdout cases: Optimizer agents receive findings ONLY from training cases. Holdout ground truth, Judge rationales, and case mappings remain strictly sealed in private data structures.

### Pattern 4: Sandboxed Per-Document Candidate Skill Optimization
**What:** Drive Gemini 3.6 Flash long-context optimizer agents to propose skill/prompt patches into candidate proposal directories without modifying repository source files.  
**When to use:** Iterative prompt and skill self-improvement.  
**Implementation Guidelines:**
1. Invoke per-document Gemini optimizer with training Judge findings for `<doc_type>`. The agent proposes candidate changes to `skills/document-agents/<doc_type>.md`.
2. Invoke shared Gemini optimizer with aggregated training findings across all document types to propose candidate changes to `AGENTS.md` and/or `skills/pdf/SKILL.md`.
3. Write candidate files to proposal sandbox directory: `proposals/candidate_<hash>/<target_file_relpath>`.
4. Validate candidate patches against allowlist rules (no case IDs, ground truth paths, synthetic applicant data, or ungrounded rules).
5. Test candidate review bundle in memory or via temporary file overlays. Accept candidate patch and commit atomically to git IF AND ONLY IF targeted training metrics improve AND zero holdout dimension regresses.

### Anti-Patterns to Avoid
- **Deterministic Semantic Fallbacks:** Substituting Python heuristic scoring or mock AnswerObjects when LLM CLI calls time out or fail. Production failures MUST be explicit and fail closed.
- **Repository CWD for Workers:** Running Worker Copilot CLI calls with cwd set to the repository root or passing `--allow-all`, which allows Workers to read research, ground truth, or source code via side-channel file tools.
- **Single-PDF Splitting:** Splitting native vector and scanned PDF variants of the same logical case between train and holdout sets, leaking defect structures across the boundary.
- **Direct Source Edits by Optimizers:** Allowing optimizer agents to write proposed patches directly to `AGENTS.md` or `skills/` before regression evaluation.
- **Fabricated Semantic Scores:** Computing LLM defect recall or grounding scores using Python string matching instead of extracting the Judge's semantic evaluation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| **Worker Staging Isolation** | Custom directory copy scripts with `shutil.copytree` | `crawler.synthetic.staging.stage_case_for_worker` | Pre-built API enforces 32-hex opaque ID checks, path containment, symlink rejection, permission normalization, clean destination assertions, and automated leakage scans. |
| **Grounding Verification** | Custom substring search or regex matchers | `crawler.grounding.check_answer_grounding` / `corpus-crawler --json ground` | Shipped, frozen grounding gate enforces exact whitespace-collapsed, case-normalized verbatim quote matching against `corpus/index.db`. |
| **JSON Extraction from LLM Output** | Regex pattern matching over raw stdout | Robust JSON decoder parser with Markdown fence stripping | Handles JSONL event streams, ANSI escape codes, triple-backtick fences, and JSON raw decode offsets safely. |
| **PDF Text Extraction** | Custom binary stream parsers | `pdfminer.high_level.extract_text` | Authoritative Python PDF text layer extractor for verifying text availability and candidate quotes. |

## Replacement Strategy for Legacy & Deterministic Paths

The existing codebase contains several legacy, fake, or partial paths identified in `74-CONTEXT.md` and `72-REVIEW.md` that must be refactored or replaced in Phase 74:

| File | Legacy State / Flaw | Phase 74 Replacement Strategy |
|------|--------------------|-------------------------------|
| `crawler/eval/pipeline_worker.py` | Prompt-only blindness, repository cwd, unrestricted permissions, and success-shaped fallback report. | **REPLACE:** Turn into truthful Gemini 3.6 Flash Worker runner (`run_blind_worker_task`) using `stage_case_for_worker`, fresh staging CWD, `--no-custom-instructions`, no tools, strict 5-field AnswerObject schema validation, and fail-closed error recording. |
| `crawler/eval/pipeline_judge.py` | Per-case judge with deterministic score fallback and a machine-specific executable path. | **REPLACE:** Turn into batched per-document Claude Opus 4.8 Judge harness (`run_batched_document_judge`) batching 10 or 12 PDFs + Worker reports + research + ground truth, with Pydantic validation and zero score fabrication. |
| `crawler/eval/real_worker.py` | Partial live call pattern; has repository access and plain-text parsing that violate blind isolation. | **REFACTOR:** Update to integrate with `stage_case_for_worker` and strict AnswerObject grounding gate; remove repo access and plain text assumptions. |
| `crawler/eval/real_judge.py` | Single-case live Judge; lacks required Phase 74 per-document batching, long-context contract, and holdout sealing. | **REFACTOR:** Upgrade to enforce per-document batching (10 or 12 cases per session), model `claude-opus-4.8` with `--effort xhigh` and `--context long_context`, and strict schema validation. |
| `crawler/eval/genuine_optimizer.py` | Hardcoded canned patcher that appends static text to `AGENTS.md`. | **REPLACE:** Replace with real Gemini agent-driven candidate optimizer (`run_candidate_optimization_pass`) writing diffs to proposal sandbox directories and evaluating train improvement + holdout non-regression. |
| `crawler/eval/agent_improvement_loop.py` | Ground-truth-derived fake Worker and simulated evaluation loop. | **DEPRECATE/REFACTOR:** Retain only as legacy benchmark wrapper or refactor to delegate to live pipeline orchestrator. |
| `crawler/eval/benchmark_runner.py` | Ground-truth-derived synthetic review generator and heuristic scorer. | **DEPRECATE/REFACTOR:** Refactor to consume live Judge evaluation reports instead of generating synthetic reviews from ground truth. |
| `crawler/eval/self_optimizer.py` | Heuristic proposal generator that simulates score deltas. | **DEPRECATE/REFACTOR:** Replace with live proposal evaluator in `patch_evaluator.py`. |

## Common Pitfalls

### Pitfall 1: Worker Isolation Side-Channel Leakage
**What goes wrong:** Worker agents infer document types or injected defects from current working directory, file paths, environment variables, or leftover cached files.  
**Why it happens:** Passing repository cwd, setting cwd to `crawler/eval/pipelines/<doc_type>/`, or leaving previous iteration reports in the execution folder.  
**How to avoid:** Stage every case into a fresh temporary directory using `stage_case_for_worker`. Run Copilot CLI inside that temporary directory with `--no-custom-instructions` and no tool permissions.  
**Warning signs:** Worker outputs citing pipeline paths or mentioning ground-truth defect IDs not observable in the document text.

### Pitfall 2: Sibling Leakage Across Train and Holdout
**What goes wrong:** Native vector PDF is placed in the training set while its 300 DPI scanned sibling is placed in the holdout set, allowing optimizer agents to overfit to the exact defect structure.  
**Why it happens:** Randomly splitting individual PDF files instead of logical case sibling pairs.  
**How to avoid:** Enforce logical sibling-group splitting in `holdout_splitter.py`. Always keep native vector and scanned sibling pairs together in either train or holdout.  
**Warning signs:** Holdout metrics showing sudden artificial jumps when training on sibling variants.

### Pitfall 3: Deterministic Score Fabrication by Python
**What goes wrong:** Python code computes semantic defect recall or grounding scores using string matching against ground truth JSON, falsely reporting the result as LLM Judge evaluation.  
**Why it happens:** Fallback logic executed when Copilot CLI calls time out or fail.  
**How to avoid:** Strict fail-closed semantics. If a Judge call fails, record `judge_error.json` and block the pipeline. Never calculate semantic scores in Python.  
**Warning signs:** Judge reports generated in milliseconds or containing hardcoded heuristic score values when Copilot CLI is unavailable.

### Pitfall 4: Prompt/Attachment Overflow in Batched Judge Sessions
**What goes wrong:** Batching 12 high-resolution scanned PDFs plus full Worker reports and research manifests exceeds prompt token or attachment payload limits in Copilot CLI.  
**Why it happens:** Scanned 300 DPI image PDFs consume substantial multimodal vision context.  
**How to avoid:** Pre-calculate total payload size. If a 12-case batch approaches CLI attachment boundaries, split into two deterministic sub-batches (e.g. 6 vector cases and 6 scanned cases) while preserving single per-document-type aggregation.  
**Warning signs:** Copilot CLI returning payload size errors or truncating JSON output.

### Pitfall 5: Unsafe Patch Acceptance
**What goes wrong:** An optimizer patch adds literal case IDs, synthetic applicant facts, or ungrounded immigration rules to `AGENTS.md` or document skills.  
**Why it happens:** Overfitting to specific training case failures.  
**How to avoid:** Run an automated patch allowlist scanner before evaluating candidate review bundles. Reject any patch containing case IDs (`case_001`), ground-truth file paths, synthetic applicant names ("Jane Doe"), or ungrounded policy claims.  
**Warning signs:** Patch proposal diffs containing specific test fixture values or file paths.

## Code Examples

### Worker Copilot CLI Invocation & AnswerObject Parsing
```python
# Source: crawler/eval/pipeline_worker.py
import json
import subprocess
from pathlib import Path
from typing import Any, Dict
from crawler.synthetic.staging import stage_case_for_worker
from crawler.grounding import check_answer_grounding

COPILOT_BIN = shutil.which("copilot")
if not COPILOT_BIN:
    raise RuntimeError("GitHub Copilot CLI executable not found")

def run_blind_worker_task(
    opaque_case_id: str,
    doc_type: str,
    public_bundle_text: str,
) -> Dict[str, Any]:
    """Execute Gemini 3.6 Flash Worker for one staged blind PDF in an isolated CWD."""
    # 1. Stage PDF into fresh temporary workspace
    staged_pdf = stage_case_for_worker(opaque_case_id)
    staging_cwd = staged_pdf.parent

    # 2. Build prompt containing public evidence bundle & document type
    prompt = f"""You are the live LLM Worker for a blind Canadian Express Entry document review.

Follow AGENTS.md and skills/pdf/SKILL.md rules. Evaluate only the blind document evidence attached.
You have NO access to ground truth specs, research reports, or injected defect labels.
Keep applicant-specific facts in basis[]; claims, quotes, abstentions, and prose must remain PII-free.
Never invent a citation or quote. If authoritative corpus evidence is missing, abstain with zero claims.

Document type: {doc_type}
Opaque case ID: {opaque_case_id}

PUBLIC REVIEW EVIDENCE BUNDLE:
<evidence_bundle>
{public_bundle_text}
</evidence_bundle>

Return ONLY one valid JSON AnswerObject with canonical fields: question, claims, basis, abstentions, prose.
Do not use Markdown code fences or commentary.
"""

    # 3. Invoke Copilot CLI in staging CWD with NO tools or custom instructions
    cmd = [
        COPILOT_BIN,
        "-p", prompt,
        "--model", "gemini-3.6-flash",
        "-s",
        "--no-custom-instructions",
    ]

    res = subprocess.run(
        cmd, cwd=str(staging_cwd), capture_output=True, text=True, timeout=300
    )
    if res.returncode != 0:
        raise RuntimeError(f"Worker Copilot CLI failed for {opaque_case_id}: {res.stderr}")

    # 4. Extract AnswerObject JSON from stream and run local grounding check
    answer = json.loads(res.stdout.strip())
    check_answer_grounding(answer)
    return answer
```

### Batched Per-Document Claude Opus Judge Execution & Schema Validation
```python
# Source: crawler/eval/pipeline_judge.py
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List
from pydantic import BaseModel, Field

class CaseScore(BaseModel):
    grounding_accuracy: float = Field(ge=0.0, le=1.0)
    citation_exactness: float = Field(ge=0.0, le=1.0)
    defect_recall: float = Field(ge=0.0, le=1.0)
    pii_containment: float = Field(ge=0.0, le=1.0)
    blind_input_compliance: float = Field(ge=0.0, le=1.0)

class CaseFinding(BaseModel):
    case_id: str
    category: str
    severity: str
    description: str

class JudgeEvaluationBatch(BaseModel):
    doc_type: str
    case_evaluations: Dict[str, CaseScore]
    findings: List[CaseFinding]
    patch_recommendations: List[Dict[str, str]]
    rationale: str

def run_batched_document_judge(
    doc_type: str,
    worker_reports: Dict[str, Dict[str, Any]],
    pdf_paths: List[Path],
    research_json: Dict[str, Any],
    ground_truth_specs: Dict[str, Dict[str, Any]],
) -> JudgeEvaluationBatch:
    """Run privileged Claude Opus 4.8 Judge for one document type batch."""
    prompt = f"""You are the privileged LLM Judge for Canadian Express Entry document review evaluation.

Model: claude-opus-4.8 (--effort xhigh, --context long_context)
Document Type: {doc_type}

Evaluate all Worker review reports against the attached blind PDFs, research findings, and ground truth specs.
Score every case on grounding_accuracy, citation_exactness, defect_recall, pii_containment, and blind_input_compliance (0.0 to 1.0).

WORKER REPORTS:
{json.dumps(worker_reports, indent=2)}

RESEARCH FINDINGS:
{json.dumps(research_json, indent=2)}

GROUND TRUTH SPECS:
{json.dumps(ground_truth_specs, indent=2)}

Return ONLY a valid JSON object matching JudgeEvaluationBatch schema.
"""

    cmd = [
        COPILOT_BIN,
        "-p", prompt,
        "--model", "claude-opus-4.8",
        "--effort", "xhigh",
        "--context", "long_context",
        "-s",
        "--no-custom-instructions",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if res.returncode != 0:
        raise RuntimeError(f"Judge Copilot CLI failed for {doc_type}: {res.stderr}")

    raw_json = json.loads(res.stdout.strip())
    return JudgeEvaluationBatch.model_validate(raw_json)
```

### Sibling Group Train/Holdout Splitter & Sealing Engine
```python
# Source: crawler/eval/holdout_splitter.py
import hashlib
from typing import Dict, List, Tuple, Any

def split_doc_type_cases(
    doc_type: str,
    logical_cases: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split logical cases into train and sealed holdout sets by sibling group.
    
    Holdout set receives:
    1. Valid control sibling pair.
    2. Exactly ONE defective sibling pair chosen deterministically via hash.
    """
    valid_controls = [c for c in logical_cases if c.get("expected_verdict") == "meets_requirements"]
    defective_cases = [c for c in logical_cases if c.get("expected_verdict") != "meets_requirements"]

    if not valid_controls or not defective_cases:
        raise ValueError(f"DocType {doc_type} missing valid control or defective cases")

    # Select valid control pair for holdout
    holdout_valid = valid_controls[:1]
    train_valid = valid_controls[1:]

    # Select 1 defective pair deterministically
    hash_val = int(hashlib.sha256(doc_type.encode("utf-8")).hexdigest(), 16)
    selected_idx = hash_val % len(defective_cases)
    holdout_defective = [defective_cases[selected_idx]]
    train_defective = [c for i, c in enumerate(defective_cases) if i != selected_idx]

    holdout = holdout_valid + holdout_defective
    train = train_valid + train_defective
    return train, holdout
```

### Sandboxed Candidate Patch Optimization & Holdout Regression Gate
```python
# Source: crawler/eval/patch_evaluator.py
from typing import Dict, Any

def evaluate_candidate_patch(
    baseline_train_metrics: Dict[str, float],
    baseline_holdout_metrics: Dict[str, float],
    candidate_train_metrics: Dict[str, float],
    candidate_holdout_metrics: Dict[str, float],
) -> bool:
    """Determine whether to accept a candidate patch.
    
    Accept IF AND ONLY IF:
    1. Targeted training score improves (candidate_train > baseline_train).
    2. Zero holdout regression across all metrics (candidate_holdout >= baseline_holdout for every score).
    """
    train_improved = candidate_train_metrics["overall_score"] > baseline_train_metrics["overall_score"]
    
    holdout_regressed = False
    for metric in ("grounding_accuracy", "citation_exactness", "defect_recall", "pii_containment"):
        if candidate_holdout_metrics.get(metric, 0.0) < baseline_holdout_metrics.get(metric, 0.0):
            holdout_regressed = True
            break

    return train_improved and not holdout_regressed
```

## Threat Model & Security Domain

### Trust Boundaries

| Boundary | Data Crossing | Enforcement |
|----------|---------------|-------------|
| Privileged Pipeline to Worker Staging | Single opaque PDF & allowed extracted text | Fresh temporary directory outside pipeline tree, `stage_case_for_worker` API, symlink/path checks. |
| Worker CLI Session to Filesystem | Worker execution commands & output | Staging CWD, `--no-custom-instructions`, no repo cwd, no tool access, local grounding gate. |
| Judge CLI Session to Ground Truth | Research, ground truth specs, Worker reports, PDFs | Dedicated privileged directory, Claude Opus 4.8 xhigh session, Pydantic schema validation. |
| Judge Output to Optimizer Agents | Training Judge findings | Filtered training findings only; holdout rationales, scores, and specs strictly sealed. |
| Candidate Proposals to Source | Proposed prompt/skill patches | Proposal sandbox directory, allowlist patch scanner, holdout regression gate, atomic git commits. |

### Threat Register

| Threat ID | Category | STRIDE | Standard Mitigation |
|-----------|----------|--------|---------------------|
| **T-74-01** | Privilege Confusion | Elevation of Privilege | Workers run in isolated staging CWD with zero repo access, no custom instructions, and no tools. |
| **T-74-02** | Case Mapping Leakage | Information Disclosure | Opaque 32-hex IDs, non-sequential filenames, and automated side-channel leakage scans on staged files. |
| **T-74-03** | PDF Attachment Escape | Tampering / Elevation | Staging API validates path containment (`is_relative_to`), rejects symlinks, and asserts clean destination. |
| **T-74-04** | Evidence Contamination | Information Disclosure | Worker prompts contain only public review bundles constructed from canonical skills and local corpus. |
| **T-74-05** | Prompt Injection | Tampering | Strict JSONL event parsing, Pydantic schema validation, local grounding gate, and no shell/tool access. |
| **T-74-06** | Cache Contamination | Spoofing | Provenance token and output SHA-256 verification; unauthenticated or stale caches are purged. |
| **T-74-07** | Ground-Truth Leakage | Information Disclosure | Judge findings sealed from Workers; holdout findings sealed from Optimizer agents. |
| **T-74-08** | Score Fabrication | Repudiation | Python prohibited from generating semantic scores; scores must originate from validated LLM Judge JSON. |
| **T-74-09** | Optimizer Overfit | Spoofing / Tampering | Logical sibling-group holdout sealing; candidates accepted only on holdout non-regression. |
| **T-74-10** | Unsafe Patches | Tampering | Automated allowlist patch scanner rejects case IDs, ground-truth paths, synthetic applicant data, or ungrounded rules. |
| **T-74-11** | Concurrent Edits | Race Condition | Candidate patches written to isolated proposal directories and committed atomically one at a time. |
| **T-74-12** | Stale Iteration Artifacts | Integrity Violation | Pipeline iterations stored in dedicated `iterations/iter_<N>/` directories with explicit cache clearing. |
| **T-74-13** | Quota Partial Completion | Denial of Service | Atomic per-case/per-document-type state recording and resume support on rate limit errors. |

### ASVS Category Mapping

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | No | CLI subprocess invocation; no web auth required. |
| V3 Session Management | No | Stateless CLI sessions per invocation. |
| V4 Access Control | Yes | Strict directory containment, temporary staging, and holdout sealing. |
| V5 Input Validation | Yes | Pydantic JSON schema validation and local grounding gate. |
| V6 Cryptography | Yes | Secrets.token_hex(16) opaque IDs, SHA-256 content hashes, and provenance tokens. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| **GitHub Copilot CLI** | Worker, Judge, & Optimizer execution | ✓ | `1.0.73` | None — mandatory runtime requirement. |
| **Python** | Orchestration & validation | ✓ | `3.10.12` | None — project virtualenv runtime. |
| **pytest** | Test automation | ✓ | `9.0.3` | None — test runner. |
| **pdfminer.six** | Text extraction | ✓ | `20260107` | None — PDF text layer extractor. |

**Missing dependencies with no fallback:** None  
**Missing dependencies with fallback:** None  

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (`9.0.3`) |
| Config file | `pyproject.toml` |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_real_llm_engine.py -v` |
| Full suite command | `.venv/bin/python -m pytest crawler/tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| `ISOLATED_PIPELINE-01` | Worker staging isolation & blindness | unit / contract | `.venv/bin/python -m pytest crawler/tests/test_phase74_worker_isolation.py -v` | ❌ Wave 0 |
| `JUDGE_IMPROVE-01` | Batched Opus 4.8 Judge & patch evaluation | unit / contract | `.venv/bin/python -m pytest crawler/tests/test_phase74_judge_loop.py -v` | ❌ Wave 0 |
| `REAL_AGENT_EXECUTION-01` | Live Copilot CLI execution & provenance | live gate | `REQUIRE_LIVE_PHASE74_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_live_phase74_conformance_gate.py -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest crawler/tests/test_phase74_worker_isolation.py crawler/tests/test_phase74_judge_loop.py -v`
- **Per wave merge:** `.venv/bin/python -m pytest crawler/tests/ -v`
- **Phase gate:** Full test suite + `REQUIRE_LIVE_PHASE74_CONFORMANCE=1` live gate green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `crawler/tests/test_phase74_worker_isolation.py` — unit tests for Worker staging isolation, AnswerObject validation, and public bundle construction.
- [ ] `crawler/tests/test_phase74_judge_loop.py` — unit tests for batched Opus 4.8 Judge schema, sibling group train/holdout splitting, and patch regression gate.
- [ ] `crawler/tests/test_live_phase74_conformance_gate.py` — live release gate verifying 236 worker reports, 23 batched judge passes, holdout evidence, and patch audit trails.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | GitHub Copilot CLI `1.0.73` handles 12 PDF attachments in a single session without context exhaustion. | Privileged Judge Execution | If context is exhausted, the Judge orchestrator must fall back to splitting into two deterministic 6-case sub-batches. |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/74-blind-report-generator-judge-self-improvement-loop/74-CONTEXT.md` - Locked implementation decisions D-01 through D-22.
- `skills/document-agents/_contract.md` - Canonical AnswerObject and grounding gate contract.
- `AGENTS.md` - Repository root system specification and PII containment rules.
- `crawler/synthetic/staging.py` - Worker staging API and leakage scanner.

### Secondary (MEDIUM confidence)
- `.planning/phases/73-blind-synthetic-document-generation-gemini-3-6-flash-long-co/73-SECURITY.md` - Proven Copilot CLI, path containment, and leakage threat mitigations.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Verified installed packages and CLI runtime (`copilot 1.0.73`).
- Architecture: HIGH — Formally constrained by locked decisions D-01..D-22 in CONTEXT.md.
- Pitfalls & Security: HIGH — Grounded in prior phase security audits and threat registers.

**Research date:** 2026-07-23  
**Valid until:** 2026-08-22 (30 days)  
