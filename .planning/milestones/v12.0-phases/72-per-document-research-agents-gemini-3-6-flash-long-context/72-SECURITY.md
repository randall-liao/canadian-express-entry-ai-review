---
phase: 72-per-document-research-agents-gemini-3-6-flash-long-context
slug: per-document-research-agents-gemini-3-6-flash-long-context
status: verified
threats_total: 10
threats_closed: 10
threats_open: 0
accepted_risks: 0
asvs_level: 1
register_authored_at_plan_time: true
last_audit: 2026-07-23
---

# Phase 72 - Security Audit Report

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Online Web to LLM Agent | Untrusted web results could contain prompt injection or false policy claims. | External untrusted text |
| LLM Agent to Pipeline | Malformed model JSON could attempt invalid writes or sibling-pipeline contamination. | Research JSON and paths |
| Subprocess to Host | Copilot and corpus CLI calls require validated executables, restricted tools, and isolated working directories. | Commands, environment, cwd |
| Concurrent Workers to Filesystem | The 23 workers must write only inside their assigned document pipeline. | Pipeline artifact paths |

## Threat Register

| Threat ID | Category | Component | Mitigation Evidence | Status |
|-----------|----------|-----------|---------------------|--------|
| T-72-01 | Tampering / Prompt Injection | Online sources | `doc_researcher.py` treats web data as untrusted and locally verifies policy assertions; `test_corpus_verification_gate` covers downgrade behavior. | closed |
| T-72-02 | Information Disclosure | Copilot cwd | Per-document cwd plus web-only available tools; `test_staging_directory_isolation` and live conformance enforce boundaries. | closed |
| T-72-03 | Input Tampering | JSONL and model payload | Strict JSONL parsing, mandatory `web_search`, Pydantic schemas, and blocked failure output. | closed |
| T-72-04 | Executable Substitution | Copilot discovery | Validated `COPILOT_PATH`/PATH discovery and publish-safe sanitized command metadata. | closed |
| T-72-05 | Gate Bypass | Stale success files | Failure handling unlinks `research.json` and `research_summary.md` before writing `research.error.json`. | closed |
| T-72-06 | Misrepresentation | Authority classification | Authoritative status requires resolved local citation and exact quote; failures downgrade to discovery. | closed |
| T-72-07 | Cross-Pipeline Collision | Concurrent workers | `_assert_in_pipeline_dir` guards every artifact path; 23-pipeline conformance checks foreign paths and unique IDs. | closed |
| T-72-08 | Provenance Tampering | Execution metadata | Live and injected engines are distinct; SHA256 prompt/output/provenance fields are checked; reasoning is excluded. | closed |
| T-72-09 | Fake Model Claims | Live gate | Live conformance requires Copilot CLI, Gemini 3.6 Flash, long context, successful return, and web-search provenance. | closed |
| T-72-10 | Partial/Stale Completion | 23-agent gate | Missing, blocked, fallback, injected, or generic artifacts fail the explicitly enabled live gate. | closed |

## Accepted Risks Log

No accepted risks.

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-23 | 10 | 10 | 0 | gsd-security-auditor |

## Sign-Off

- [x] All threats have a disposition.
- [x] No high-severity gap was accepted.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set.

**Approval:** verified 2026-07-23
