---
phase: 74-blind-report-generator-judge-self-improvement-loop
plan: 05
status: complete
subsystem: evaluation
tags: [copilot-sdk, concurrency, cleanup, provenance, holdout, optimization]

requires:
  - phase: 74-04
    provides: SDK-supervised isolated document pipelines
provides:
  - Authenticated official-SDK access to mandatory Gemini and Opus models
  - Eleven measured parent-serialized document skill patches
  - Complete 23-document live optimization evidence
  - Worker model-input identifier isolation with TDD evidence
  - Complete immutable 236-Worker and 23-Judge final pass
  - PII-safe final hash/provenance evidence for all 23 document types
  - Green strict live conformance gate
affects: [phase-74, phase-75, live-conformance]

tech-stack:
  added: []
  patterns:
    - Copilot CLI OAuth credential is validated and forwarded in memory only
    - SDK blob attachments use documented camelCase JSON-RPC fields
    - Candidate semantic failures reject proposals without weakening strict parsing
    - Worker case identity is parent-only and never model-visible
    - Syntax-only JSON repair uses one canonically recorded turn in the same SDK session
    - Spawn identity registration waits through a bounded visibility window
    - Judge structural correction shares the same single-turn budget
    - Exact Worker outputs reconcile across parent-only revisions
    - Worker AnswerObject structure correction is generic and semantic-free
    - Final completion is gated only by committed canonical evidence
    - Raw Judge SDK responses and sanitized score payloads have distinct externally pinned hashes

key-files:
  created:
    - .planning/phases/74-blind-report-generator-judge-self-improvement-loop/74-05-SUMMARY.md
  modified:
    - crawler/eval/copilot_sdk_runtime.py
    - crawler/eval/agent_runtime.py
    - crawler/eval/genuine_optimizer.py
    - crawler/eval/document_pipeline.py
    - crawler/eval/pipeline_worker.py
    - crawler/eval/loop_orchestrator.py
    - crawler/eval/pipeline_state.py
    - crawler/eval/sdk_pipeline_orchestrator.py
    - crawler/eval/phase74_evidence.py
    - crawler/tests/test_copilot_sdk_runtime.py
    - crawler/tests/test_phase74_sdk_roles.py
    - crawler/tests/test_phase74_document_pipeline.py
    - crawler/tests/test_phase74_worker_isolation.py
    - crawler/tests/test_phase74_judge_loop.py
    - crawler/tests/test_phase74_sdk_pipeline.py
    - crawler/tests/test_live_phase74_conformance_gate.py
    - crawler/tests/test_phase74_committed_evidence.py
    - skills/document-agents/digital-photos.md
    - skills/document-agents/letter-of-explanation.md
    - skills/document-agents/marriage-certificate.md
    - skills/document-agents/medical.md
    - skills/document-agents/other-name.md
    - skills/document-agents/proof-of-studies.md

key-decisions:
  - "Use only the Copilot CLI credential validated in private local storage for official SDK JSON-RPC execution."
  - "Reject malformed candidate evaluations conservatively while keeping baseline source; transport failures remain blocking."
  - "Mark Phase 74 complete only after the immutable final pass and strict live gate succeed."
  - "Keep opaque case IDs and input hashes out of Worker prompts/attachments; attach deterministic identity only after validation."
  - "Permit one syntax-only format correction in the same SDK session; parsed semantic failures remain immediately blocking."
  - "Register child identity from one bounded observed snapshot to avoid a second /proc visibility race."
  - "Allow one sanitized same-session Judge structural correction without changing semantic output in Python."
  - "Reuse Worker reports only after full current input/provenance validation; rebuild parent wrappers, never model output."
  - "Allow one generic same-session Worker structure correction while keeping grounding, PII, blindness, and semantic failures non-correctable."
  - "Final conformance reads only committed per-case evidence and never ignored baseline, reports, or loop-summary state."
  - "Bind each raw Judge SDK response to an independently hashed PII-free score payload through a pinned 23-record sanitization set."

patterns-established:
  - "Live candidate validation failure: strict malformed output becomes an audited rejection, never an accepted patch."
  - "Cleanup after interrupted live work quarantines manifest-owned state and releases the lease with zero remaining PIDs."

requirements-completed:
  - ISOLATED_PIPELINE-01
  - JUDGE_IMPROVE-01
  - REAL_AGENT_EXECUTION-01

duration: 8h 31m
completed: 2026-07-26
---

# Phase 74 Plan 05: SDK Self-Improvement Pass Summary

**Official SDK optimization with eleven measured patches, complete shared
evaluation, and an immutable 236-Worker/23-Judge final pass validated by the
strict live conformance gate.**

## Performance

- **Original blocked execution:** 12m 37s
- **Continuation:** 2h 22m 42s
- **Prompt-decontamination continuation:** 13m 16s
- **Reliability-hardening continuation:** 19m 29s
- **Judge-correction continuation:** 1h 29m 20s
- **Worker-correction continuation:** 1h 19m 35s
- **Grounding-correction completion:** 2h 33m 36s
- **Final fresh attempt:** approximately 59m 43s
- **Corrected fresh attempt:** approximately 6m 17s
- **Targeted suite:** 269 passed, 21 subtests passed in 66.83s
- **Live gate:** 68 passed, 1 failed in 1.92s
- **Reliability suite:** 354 passed, 1 skipped, 21 subtests in 57.70s
- **Latest live gate:** 77 passed, 1 failed in 1.10s
- **Judge-corrected suite:** 365 passed, 1 skipped, 21 subtests in 67.19s
- **Judge-corrected live gate:** 79 passed, 1 failed in 1.24s
- **Worker-corrected suite:** 376 passed, 1 skipped, 21 subtests in 61.09s
- **Worker-corrected live gate:** 81 passed, 1 failed in 1.20s
- **Final targeted suite:** 382 passed, 1 skipped, 21 subtests in 77.98s
- **Final strict live gate:** 83 passed in 2.11s
- **Evidence-review suite:** 528 passed, 1 skipped, 21 subtests
- **Committed-only gate:** 83 passed with ignored reports access denied
- **Publish safety:** 1,572 tracked files, zero violations

## Accomplishments

- Resolved the OAuth/model-discovery blocker without printing or persisting the
  credential.
- Verified official SDK 1.0.8, runtime 1.0.73, protocol 3, and both mandatory
  model IDs.
- Fixed SDK blob JSON-RPC attachment encoding.
- Added bounded recovery for empty SDK terminal responses and strengthened raw
  optimizer JSON instructions without accepting fenced Judge output.
- Distinguished candidate semantic failures from infrastructure failures:
  malformed candidates are rejected, while source and holdout remain safe.
- Applied nine measured patches through parent-only serialized atomic commits.
- Completed a fresh 23-document optimization phase with 236 baseline Workers,
  23 baseline Judges, and 23 optimizers at five-slot peak concurrency.
- Preserved cleanup and blocked-run audit evidence with zero remaining PIDs.
- Removed case IDs, hashes, and internal filenames from exact Worker
  AgentRequest model input while preserving parent-side identity metadata.
- Confirmed the prompt change invalidates prior Worker reuse hashes.
- Added one same-session, syntax-only JSON framing correction with complete
  canonical turn provenance and live-gate tamper checks.
- Closed the child identity `/proc` race with bounded observation, atomic
  registration, fast-exit reconciliation, and exact-handle cleanup.

## Runtime and Model Provenance

| Role | Model | Effort | Context | Engine |
|---|---|---|---|---|
| Worker | `gemini-3.6-flash` | none | `long_context` | `copilot-sdk` |
| Optimizer | `gemini-3.6-flash` | none | `long_context` | `copilot-sdk` |
| Judge | `claude-opus-4.8` | `xhigh` | `long_context` | `copilot-sdk` |

Execution used official SDK JSON-RPC only. No prompt CLI path, fallback
evaluator, model substitution, reduced tier, or lowered effort was used.

## Accepted Skill Patches

Nine accepted patches came from the original audited execution sequence. Two
post-review fresh attempts added `a2c6497` and `b00e9cf`; the release-valid run
`sdk-20260727T082623Z-539def5d2bd9` accepted no additional patch and rejected
all 23 proposals. Every accepted record satisfies the production rule:
positive training overall delta, non-regressing training safety dimensions,
and zero holdout-dimension regression. Canonical cumulative records are linked
from `crawler/eval/phase74_evidence/accepted_patches.json`.

| Document | Commit | Training delta |
|---|---|---:|
| Digital photo | `b2dfc21` | +0.010000 |
| Letter of explanation | `9b5b8b5` | +0.133333 |
| Marriage certificate | `2c4000e` | +0.023333 |
| Medical examination | `90d6aab` | +0.060000 |
| Proof of other name | `64e2e0a` | +0.075000 |
| Proof of studies | `1fe4e35` | +0.006667 |
| Medical examination, second refinement | `7975782` | +0.023333 |
| Employment reference letter | `0607175` | +0.010000 |
| Letter of explanation, second refinement | `bbe1e46` | +0.051667 |
| Letter of explanation, third refinement | `a2c6497` | +0.001667 |
| Proof of other name, second refinement | `b00e9cf` | +0.091667 |

All optimizer inputs were training-only. Sealed holdout commitments remained
local and were never included in optimizer model inputs.

## Worker Opaque-ID Root-Cause Fix

The original Worker prompt explicitly included `OPAQUE CASE ID`, exposed the
public-bundle SHA-256, and used the opaque ID as the blob/staging filename.
None was necessary for model reasoning.

TDD now verifies the exact Worker `AgentRequest`:

- prompt contains no case ID, PDF/input hash, bundle hash, or internal path;
- attachment display and staging names are neutral (`document.pdf` and
  `document.txt`);
- `_assert_answer_blindness_and_pii` is unchanged;
- Python adds `case_id` and `doc_type` only after strict AnswerObject,
  grounding, blindness, and PII validation;
- provenance still binds PDF, extracted-text, bundle, prompt, output, and
  answer hashes outside model-visible input.

The RED and GREEN commits are `e17838d` and `ea04cbb`.

## SDK Framing and Spawn Reliability

Sanitized certified-translation evidence persisted only the strict parser
classification; it contained no raw model output or assistant event, so the
failure can be truthfully classified only as syntax/framing, not specifically
fenced versus prose-prefixed versus truncated JSON.

The SDK now permits one correction turn only when the first non-empty assistant
content cannot be parsed as JSON. It uses the same session, sends no attachment
or new evidence, and never repeats the initial prompt. A second malformed
response fails. Any syntactically valid value proceeds to unchanged role
schema, grounding, PII, blindness, Judge coverage, and allowlist checks without
correction.

Canonical provenance and digests now require turn count, correction count,
initial/correction prompt hashes, ordered response hashes, final output hash,
and the same session ID for every turn. Old schemas and inconsistent correction
records fail artifact reuse and live conformance.

The supervisor now probes exact-handle PID identity for a bounded 100ms window.
Delayed identity is atomically registered from the observed snapshot; fast exit
reconciles terminal manifest/result; never-visible live handles use bounded
terminate/escalate/await and retain the lease if unreaped.

TDD commits: `a2d9fce` and `583f2a7`.

## Judge Structural Correction and Artifact Reconciliation

TDD commits `40a1d30` and `cbd1ead` add one same-session Judge correction for
syntactically valid JSON that fails strict batch schema, document identity,
exact case coverage, or finding-ID membership. The correction contains only
sanitized validation categories and the exact allowed document/case IDs
already in the Judge prompt. It contains no evidence, private facts, paths, or
suggested semantic values.

The syntax and Judge corrections share one total turn budget. Canonical
provenance conditionally records `correction_kind` and binds correction count,
prompt hash, response chain, and same-session identity. Valid one-turn Worker
artifacts retain their original canonical schema.

The artifact importer validates unchanged Worker output against current
prompt, bundle, PDF/text, corpus, model, SDK, output hash, and canonical
provenance. It allows only parent-side stage, selection, and source revision to
change, then reconstructs a current stage wrapper and import audit. It never
rewrites model output or provenance.

## Worker AnswerObject Structural Correction

TDD commits `4f593f9` and `e167eb5` add a generic `worker_structure`
same-session policy. It validates only exact canonical top-level fields,
claim/basis/abstention container and member types, exact nested keys, and the
`not_in_corpus` abstention reason enum before SDK session teardown.

One sanitized correction may restate only the generic schema and structural
error categories. It receives no original output, case identity, paths,
applicant facts, evidence, or defect labels and shares the single turn budget
with syntax/Judge correction. Grounding, exact quotes, PII, blindness, and all
semantic checks remain unchanged, local, and non-correctable.

Commit `c072dd8` expands audited import discovery to every complete Worker stage
from the latest supervisor run. Each candidate artifact is independently
validated; zero-correction artifacts remain canonical and are not invalidated
by the new capability.

## Historical Completed Run (Superseded)

- **Run ID:** `sdk-20260726T005337Z-14e36ab1aa5f`
- **Supervisor status:** completed
- **Observed peak concurrency:** 5
- **Optimization documents:** 23 / 23
- **Shared baseline:** 23 / 23
- **Shared candidate evaluation:** 23 / 23
- **Final Workers:** 236 / 236
- **Final Judges:** 23 / 23
- **Exact imported stages:** 82
- **Correction turns:** 4 syntax, 3 legacy Worker-structure, 57 combined Worker-validation
- **Current-run patches:** 2 accepted / 21 rejected
- **Shared candidate:** rejected after all 23 document evaluations
- **Final source revision:** `bbe1e46`
- **Final manifest:** `01ce99c33654900bccaafceba3da0cb6a0d2b977f21de4c492921d6100eb2743`

Both current-run patches improved training metrics and had no negative holdout
dimension. Together with seven preserved earlier commits, the immutable source
contains nine measured patch commits.

Raw Worker/Judge outputs remain in gitignored SDK state because basis and
privileged findings may contain synthetic applicant facts. Commit `235d29c`
publishes PII-safe evidence for every final report: canonical hashes,
provenance digests, complete case/score coverage, final source/manifest
bindings, and proposal audits.

Review commit `19f2c81` replaces those aggregate-only exports with independently
verifiable committed evidence:

- root manifest:
  `crawler/eval/phase74_evidence/manifest.json`
- 23 document directories with exactly 236 per-case Worker records, 23 Judge
  records, and 23 shared-evaluation records
- cumulative nine-patch audit:
  `crawler/eval/phase74_evidence/accepted_patches.json`
- final-run 21 rejected decisions:
  `crawler/eval/phase74_evidence/rejected_patches.json`
- sanitized concurrency, cleanup/reconciliation, and frozen-manifest evidence

Every object and file is canonically hashed and cross-linked. The cumulative
audit contains all nine accepted commits; exactly two records (`0607175`,
`bbe1e46`) belong to the final completed run.

Evidence contract hardening in `56f87cd` pins SDK `1.0.8`, runtime `1.0.73`,
protocol `3`, Gemini Worker/optimizer and Opus Judge role configuration. Strict
extra-forbid schemas validate every nested record. The gate independently
recomputes all accepted/rejected/shared metric deltas and enforces the exact
seven-earlier/two-final accepted attribution, 2+21 final decision partition,
shared rejection, source/CAS/commit/trailer bindings, and coordinated-tamper
resistance. Prior review manifest:
`7adfdee056112e6b258d7b17fee4ebfa23cde4b74870510f4971e2d33acf028b`.

Coordinated-tamper hardening in `e6ae394` upgrades every nested scalar to
strict typed hashes/IDs/timestamps/finite metrics, rebuilds Judge input
manifests from tracked research, ground truth, PDFs, and Worker hashes,
recomputes proposal/shared decisions, and cross-links all 93 sanitized process
instances through concurrency, cleanup, and the final evidence manifest.
Prior coordinated-tamper manifest:
`23e4a2f9815f94856b32d2544c38a627529f307250d25d633d2c33f9b67e805a`.

Final sanitization in `90cff43` enforces the exact evidence filesystem
inventory, removes all ignored corpus reads from the gate, publishes 25
citation commitments plus 46 tracked research/ground-truth commitments,
recomputes every Judge input manifest from 10/12 tracked PDFs and Worker
hashes, fixes the shared target to `skills/pdf/SKILL.md`, validates rejected
source revisions/targets, and cross-links the exact 1+23+23+23+23 process
partition. Prior final-sanitization manifest:
`1fe0dea9947aef9b41ac228e82f46a09e8dd9d4cdc0fd17b2bfc0c15e1de3828`.

Citation/lifecycle closure in `29092eb` pins the exact 25-citation commitment set
(`c6a01948386711fd259ec112c20e5a90a78567de67bf0fc1b41c1695810e2105`),
enforces 289 subordinate/290 total evidence files, records 186 lifecycle events
for exactly 93 paired process instances, removes all ignored corpus access from
the gate, and binds rejected source revisions and the canonical shared candidate.

Final Judge/lifecycle closure in `473787d` derives each `raw_output_hash`
directly from immutable SDK provenance, hashes an explicit PII-free
`sanitized_evaluation_payload` independently, and pins all 23 raw-to-sanitized
bindings under
`0d6797b530db96f0c503891077d040ec6b219f9639100dd339eb011503ea7a3c`.
The 186 lifecycle events are globally ordered with exact sequence and
active-before/after transitions from zero to peak five and back to zero. Current
evidence manifest:
`a96f9c4f954c020fd057cb6c003e85bca691fab3b85111f1c4c474bd6928060f`.

## Release-Valid Fresh Run

- **Run ID:** `sdk-20260727T082623Z-539def5d2bd9`
- **Supervisor status:** completed
- **Observed peak concurrency:** 5
- **Optimization documents:** 23 / 23
- **Shared baseline:** 23 / 23
- **Shared candidate evaluation:** 23 / 23
- **Final Workers:** 236 / 236
- **Final Judges:** 23 / 23
- **Optimizers:** 23 / 23
- **Imported model artifacts:** 0
- **Current-run patches:** 0 accepted / 23 rejected
- **Cumulative accepted patches:** 11
- **Shared candidate:** rejected after all 23 document evaluations
- **Final source revision:** `7a83a0100c2b064defe2a441f3a3db38aec4877f`
- **Final manifest:** `9af44262a2a2cf09411fd14792bf437dfac99e06960ea51eb8247cf9eb292f59`
- **Committed evidence manifest:** `3c59e9b94802556e80de1685f4f3118a8f842548e3ba2f9c9e668e5ecfe3b811`
- **Process cleanup:** 93 / 93 reaped, zero survivors, lease released

The fresh committed-only gate contains 236 per-case Worker records, 23 Judge
records, 23 shared-evaluation records, explicit optimizer/import counts, the
ordered 11-patch audit, the final 0+23 decision partition, and PII-safe
concurrency/cleanup/frozen-source commitments. Raw model artifacts remain in
gitignored local state.

## Cleanup Audit

- Initial continuation cleanup quarantined two obsolete blocked preflight
  manifests.
- Each failed/interrupted attempt used ownership-safe dry-run and apply cleanup.
- Final audit ID:
  `20260725T203221649062Z-c7f38bc9`.
- Final apply quarantined six stopped shared-baseline namespaces, released the
  retained lease, and reported zero errors, zero remaining PIDs, and zero
  forced terminations.
- SDK state, logs, prompts, reasoning, and audit directories remain ignored.
- Corrected-run audit
  `20260725T205103077168Z-0a60def2` quarantined six child namespaces,
  released the retained lease, and found zero remaining PIDs, forced
  terminations, or errors.
- Reliability-run audit
  `20260725T211706609868Z-39104352` quarantined six child namespaces,
  released the retained lease, and reported zero remaining PIDs,
  terminations, or errors.
- Judge-corrected audit
  `20260725T224956573606Z-46c4033e` quarantined six blocked/in-flight
  namespaces, released the lease, and reported zero remaining PIDs,
  terminations, or errors.
- Worker-corrected audit
  `20260726T001241344020Z-1da7e877` quarantined four blocked/in-flight
  namespaces, released the retained lease, and reported zero remaining PIDs,
  terminations, or errors.
- The completed run reconciled every child and released its lease without a
  cleanup pass; zero run-owned processes remain.

## Post-Evaluation Release Harness Hardening

Commits `1b0de0f`, `59e3d93`, `a2ce3d3`, and `8144956` classify SDK
process/client ownership failures as infrastructure, preserve lifecycle and
timeout types through Worker, Judge, and optimizer layers, and keep them out of
deterministic candidate rejection. This hardening occurred after the frozen
live evaluation; the 236/23 evidence remains bound to revision `bbe1e46` and
was not regenerated.

## Verification

- Complete non-live Phase 74 suite before final execution: **PASS**
  - 742 tests passed
  - 200,371 subtests passed
- `REQUIRE_LIVE_PHASE74_CONFORMANCE=1` gate: **PASS**
  - 83 tests passed
- Committed coordinated-tamper suite: **PASS**
  - 140 tests passed
- Gate independence: **PASS** with all reads beneath ignored `reports/`
  configured to fail
- Publish safety: **PASS**, zero violations
- `iter_sdk_final` document directories: **23 / 23**
- Published final evidence: **236 Workers / 23 Judges**
- Active run-owned processes after cleanup: **0**

## Blockers Resolved

Authentication, prompt contamination, framing, spawn identity, Judge coverage,
Worker structure, and Worker grounding blockers are resolved. The final run
completed without lowering models, effort, counts, strict validation, or
isolation.

## Task Commits

1. `9964037` — encode SDK blob attachments correctly
2. `82aff7c` — harden live response recovery
3. `b2dfc21` — apply digital photo patch
4. `9b5b8b5` — apply letter of explanation patch
5. `2c4000e` — apply marriage certificate patch
6. `90d6aab` — apply medical examination patch
7. `64e2e0a` — apply proof of other name patch
8. `1fe4e35` — apply proof of studies patch
9. `f11e1f4` — reject invalid candidate evaluations safely
10. `e17838d` — expose Worker identifier contamination with failing tests
11. `ea04cbb` — remove Worker case identifiers from model input
12. `a2d9fce` — expose SDK correction and spawn races with failing tests
13. `583f2a7` — harden same-session framing and child identity registration
14. `40a1d30` — expose Judge correction and exact artifact-import requirements
15. `cbd1ead` — implement same-session Judge correction and Worker reconciliation
16. `7975782` — apply second medical-examination refinement
17. `4f593f9` — expose Worker AnswerObject structural correction gap
18. `e167eb5` — implement same-session Worker structural correction
19. `c072dd8` — reuse exact Worker stages across audited runs
20. `5fcd4c1` — expose Worker grounding correction gap
21. `5d46c31` — implement same-session Worker grounding correction
22. `699ab02` — expose exact Judge artifact import gap
23. `9484a82` — reuse exact Judge stages across runs
24. `b6cc838` — expose candidate response-validation classification
25. `b52cf51` — classify deterministic candidate validation failures
26. `96ca0dd` — reconcile model artifacts across audited runs
27. `0607175` — apply employment-reference-letter refinement
28. `bbe1e46` — apply second letter-of-explanation refinement
29. `235d29c` — publish PII-safe completed final evidence
30. `74e7e10` — expose committed-evidence trust and ownership PID gaps
31. `19f2c81` — publish canonical committed evidence and committed-only gate
32. `c4c1ae9` — stabilize bounded lifecycle assertions
33. `56f87cd` — pin runtime facts and recompute all evidence decisions
34. `e6ae394` — close coordinated scalar, Judge, proposal, and process tampering
35. `90cff43` — close final inventory, corpus, binding, and sanitization gaps
36. `29092eb` — pin citation set and exact process lifecycle evidence
37. `473787d` — anchor Judge sanitization pairs and global lifecycle ordering
38. `1b0de0f` — expose lifecycle failure misclassification
39. `59e3d93` — preserve typed lifecycle failures through role layers
40. `a2ce3d3` — preserve frozen evaluation binding after harness hardening
41. `8144956` — preserve sanitized Judge process failures as infrastructure

## Decisions Made

- Used the validated Copilot CLI OAuth credential in process memory only.
- Preserved strict Worker/Judge output contracts rather than stripping or
  accepting malformed live output.
- Applied only candidates with positive training delta and no holdout
  dimension regression.
- Marked Phase 74 complete only after the final pass and live gate succeeded.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected SDK attachment wire keys**
- **Found during:** first authenticated fresh run
- **Issue:** Blob attachments used Python snake_case keys, causing the runtime
  to receive undefined MIME/display values.
- **Fix:** Switched to documented `mimeType` and `displayName` fields and added
  regression assertions.
- **Committed in:** `9964037`

**2. [Rule 2 - Missing Critical] Added bounded empty-response recovery**
- **Found during:** second authenticated run
- **Issue:** An empty SDK terminal response blocked a Worker without using the
  existing bounded transient retry policy.
- **Fix:** Classified empty terminal content as transient and strengthened the
  optimizer's raw-JSON instruction.
- **Committed in:** `82aff7c`

**3. [Rule 1 - Bug] Rejected invalid candidate evaluations safely**
- **Found during:** hardened live optimization
- **Issue:** Candidate-only malformed output blocked the document instead of
  rejecting the candidate, despite valid baseline evidence.
- **Fix:** Added typed semantic rejection evidence while keeping transport
  errors blocking and strict parsers unchanged.
- **Committed in:** `f11e1f4`

**4. [Rule 1 - Bug] Removed Worker identity contamination at its source**
- **Found during:** corrected shared-baseline diagnosis
- **Issue:** The Worker prompt and attachment/staging names exposed the opaque
  case ID and avoidable hash metadata to the model.
- **Fix:** Neutralized model-visible filenames, removed case/hash identifiers
  from the prompt, preserved strict output rejection, and retained identity
  only in post-validation metadata/provenance.
- **Committed in:** `e17838d`, `ea04cbb`

**5. [Rule 2 - Missing Critical] Added bounded same-session framing correction**
- **Found during:** certified-translation baseline Worker diagnosis
- **Issue:** A syntax-only response framing failure had no safe in-session
  recovery and opening a replacement Worker session would violate isolation.
- **Fix:** Added one syntax-only correction turn in the same session with
  canonical turn provenance; semantic failures remain non-correctable.
- **Committed in:** `a2d9fce`, `583f2a7`

**6. [Rule 1 - Bug] Closed child identity visibility race**
- **Found during:** death-certificate child spawn
- **Issue:** The parent immediately re-probed `/proc` and could fail
  registration during short PID identity visibility delay.
- **Fix:** Added a bounded probe window, atomic observed-identity registration,
  fast-exit reconciliation, and exact-handle cleanup.
- **Committed in:** `a2d9fce`, `583f2a7`

**7. [Rule 2 - Missing Critical] Added bounded Judge structural correction**
- **Found during:** certificate-of-qualification baseline Judge
- **Issue:** Parsed JSON could be structurally self-inconsistent with the exact
  batch identity/coverage and the SDK session closed before correction.
- **Fix:** Added one sanitized same-session structural correction sharing the
  syntax budget, with conditional correction-kind provenance and no Python
  semantic mutation.
- **Committed in:** `40a1d30`, `cbd1ead`

**8. [Rule 2 - Missing Critical] Added exact Worker artifact reconciliation**
- **Found during:** resume planning after a parent-only Judge code change
- **Issue:** Run isolation prevented reuse of exact Worker outputs even though
  their model-visible inputs and provenance were unchanged.
- **Fix:** Added validated import that compares every Worker binding and
  reconstructs only parent stage metadata with an audit.
- **Committed in:** `40a1d30`, `cbd1ead`

**9. [Rule 2 - Missing Critical] Added bounded Worker structure correction**
- **Found during:** death-certificate shared-baseline Worker
- **Issue:** Syntactically valid AnswerObject JSON could contain malformed
  canonical containers after the SDK session closed.
- **Fix:** Added one generic same-session structural correction with
  `worker_structure` provenance; semantic/local gates remain non-correctable.
- **Committed in:** `4f593f9`, `e167eb5`

**10. [Rule 2 - Missing Critical] Expanded exact Worker-stage discovery**
- **Found during:** shared-baseline resume
- **Issue:** The importer considered only baseline artifacts from quarantine,
  excluding exact completed shared/candidate stages.
- **Fix:** Discover all completed Worker stages from the latest audited run and
  validate each independently before parent wrapper reconciliation.
- **Committed in:** `c072dd8`

**11. [Rule 2 - Missing Critical] Added combined Worker grounding correction**
- **Found during:** medical-examination shared baseline
- **Issue:** Structurally valid claims could fail exact local quote grounding
  only after the SDK session closed.
- **Fix:** Combined structure and grounding in one typed same-session policy
  using sanitized categories and no Python semantic mutation.
- **Committed in:** `5fcd4c1`, `5d46c31`

**12. [Rule 1 - Bug] Classified candidate validation failures semantically**
- **Found during:** resumed medical candidate evaluation
- **Issue:** Exhausted deterministic correction budget was classified as SDK
  infrastructure and blocked the safe baseline final path.
- **Fix:** Added `ResponseValidationError`, allowing candidate-only failures to
  reject while preserving transport failures as blockers.
- **Committed in:** `b6cc838`, `b52cf51`

**13. [Rule 2 - Missing Critical] Published PII-safe final evidence**
- **Found during:** final artifact publication
- **Issue:** Raw final basis/findings can contain synthetic applicant facts that
  must not enter git history.
- **Fix:** Kept raw outputs in ignored SDK state and published hashes,
  provenance, case/score coverage, manifest bindings, and patch audits.
- **Committed in:** `235d29c`

**14. [Rule 2 - Missing Critical] Made final evidence independently verifiable**
- **Found during:** Task 6 committed-evidence review
- **Issue:** The live gate depended on ignored baseline/loop-summary state and
  aggregate committed evidence could not prove per-case final execution,
  concurrency, cleanup, shared evaluation, or cumulative patches.
- **Fix:** Published canonical per-case Worker/Judge/shared records,
  concurrency/cleanup/frozen-manifest evidence, all nine accepted audits, all
  final-run rejections, and a committed-only tamper-tested gate.
- **Committed in:** `74e7e10`, `19f2c81`

**15. [Rule 2 - Missing Critical] Pinned runtime and recomputed decisions**
- **Found during:** final committed-evidence review
- **Issue:** Coordinated runtime tampering, permissive nested fields, and stored
  patch/shared deltas were not independently constrained.
- **Fix:** Added exact runtime constants, extra-forbid nested schemas,
  deterministic metric/delta recomputation, 9-record cumulative ordering,
  2+21 final partitioning, shared rejection validation, and tamper tests.
- **Committed in:** `56f87cd`

**16. [Rule 2 - Missing Critical] Closed coordinated evidence tampering**
- **Found during:** final evidence adversarial review
- **Issue:** Coordinated redigests could alter scalar identities, Judge input
  bindings, proposal identities, shared aggregates, or process traces.
- **Fix:** Added strict scalar types, tracked-fixture Judge recomputation,
  canonical candidate/run bindings, shared aggregate recomputation, and exact
  93-instance concurrency/cleanup cross-links with 89 tamper tests.
- **Committed in:** `e6ae394`

**17. [Rule 2 - Missing Critical] Closed final evidence sanitization gaps**
- **Found during:** final filesystem/corpus/binding review
- **Issue:** Extra filesystem entries, ignored corpus access, model-controlled
  correction IDs, and incomplete Judge/proposal/process cross-links remained.
- **Fix:** Added exact recursive inventory, corpus commitments, tracked-fixture
  Judge recomputation, canonical shared/rejected/source bindings, 93-instance
  stage partitioning, and adversarial sanitization tests.
- **Committed in:** `90cff43`

**18. [Rule 2 - Missing Critical] Pinned citation and lifecycle evidence**
- **Found during:** final external-commitment review
- **Issue:** Citation sets remained self-referential and lifecycle/Judge/shared
  hash semantics lacked exact immutable pairing.
- **Fix:** Pinned the 25-citation set, enforced exact recursive inventory,
  removed corpus DB reads, paired all 93 process lifecycles, strengthened
  Judge/proposal/shared bindings, and removed model claim IDs from corrections.
- **Committed in:** `29092eb`

**19. [Rule 2 - Missing Critical] Anchored Judge sanitization and global lifecycle order**
- **Found during:** final coordinated-tamper review
- **Issue:** Judge raw and sanitized artifact hashes lacked an external
  raw-to-sanitized set anchor, and process events did not prove one global
  chronological active-count transition sequence.
- **Fix:** Published exact extra-forbid sanitized score payloads, pinned all 23
  raw/artifact/input bindings, and recorded 186 globally ordered lifecycle
  events with strict UTC timestamps, unique sequence IDs, and exact active
  counts.
- **Committed in:** `473787d`

**20. [Rule 1 - Bug] Preserved infrastructure failure classification**
- **Found during:** final candidate-classification review
- **Issue:** A missing SDK process handle was mislabeled as deterministic
  response validation, and Judge/optimizer wrappers could turn runtime failures
  into candidate rejection.
- **Fix:** Added `AgentLifecycleError`, preserved all infrastructure types
  through role layers, and restricted the semantic tuple to deterministic
  validation errors.
- **Committed in:** `1b0de0f`, `59e3d93`, `a2ce3d3`, `8144956`

## Authentication Gate

The original blocker is resolved. The private local credential exposed both
mandatory model IDs through official SDK preflight. No authentication data was
persisted in artifacts.

## Known Stubs

These are intentional authoring templates, not runtime data stubs:

| File | Lines | Reason |
|---|---:|---|
| `skills/document-agents/digital-photos.md` | 76 | Example tells reviewers to replace tokens with exact corpus/private values. |
| `skills/document-agents/letter-of-explanation.md` | 75, 98 | Example quote and basis tokens must be replaced. |
| `skills/document-agents/marriage-certificate.md` | 74, 97 | Example quote and basis tokens must be replaced. |
| `skills/document-agents/other-name.md` | 70, 93 | Example quote and basis tokens must be replaced. |
| `skills/document-agents/proof-of-studies.md` | 76, 99 | Example quote and basis tokens must be replaced. |

## Deferred Issues

None.

## Next Phase Readiness

Phase 74 is **complete**. Phase 75 may consume the frozen manifest, PII-safe
final evidence, patch audits, and green live conformance result.

## Self-Check: PASSED

All referenced continuation commits and their modified
source/test/skill/evidence files were verified. The summary, ignored SDD report,
and completed state update exist on disk; publishable evidence contains no
token, raw prompt/reasoning, PII sentinel, or absolute private path.

---
*Phase: 74-blind-report-generator-judge-self-improvement-loop*
*Completed: 2026-07-26*
