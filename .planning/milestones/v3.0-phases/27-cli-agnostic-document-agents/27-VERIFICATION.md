---
phase: 27-cli-agnostic-document-agents
verified: 2026-06-21T14:55:46Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
re_verification:
  # No previous VERIFICATION.md existed — initial verification.
requirements:
  - id: CHK-03
    status: satisfied
    evidence: "Six CLI-agnostic markdown document agents consume the search contract and emit only gated, cited claims; conformance proven by run_eval (8/8 pass, failed=0) + 16/16 conformance tests."
---

# Phase 27: CLI-Agnostic Document Agents — Verification Report

**Phase Goal:** Six portable plain-Markdown document-agent skills (police certificate, language test, ECA, proof of funds, medical, employment reference letter) answer document questions by consuming the `search` contract and emitting only gated, cited claims — identically across CLIs.
**Verified:** 2026-06-21T14:55:46Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Six plain-Markdown agents exist (no front-matter, link `_contract.md`, bake a query not a `#NNN` chunk_id, no inlined volatile values, no bare-python) | ✓ VERIFIED | All 6 files present under `skills/document-agents/` (40–184 lines each). Independent grep: every first line is `# Heading` (not `---`); 0 `#NNN` chunk_ids in bodies; 0 bare-python; each links `_contract.md`. `TestSkillsStaticGate` (7 tests) green. |
| 2 | Shared `_contract.md` documents the 5-key answer object, the search→copy-verbatim-quote→ground loop, the three fail reasons, and the abstention rule | ✓ VERIFIED | `_contract.md` (226 lines): §"structured answer object" lists `question/claims/basis/abstentions/prose`; §"grounding-by-construction loop" (search→resolve→verbatim-quote→ground→abstain); fail-reason table (`uncited`/`unresolvable`/`quote_not_in_chunk`); §"abstention rule — abstain, never confabulate". |
| 3 | Grounding-by-construction + abstention: confab line fails closed, must_abstain passes with zero claims, all six agent answers ground `verdict:"pass"` | ✓ VERIFIED | `crawler.cli --json ground --eval … --db corpus/index.db` → `ok:true, total 8, passed 8, failed 0`, exit 0. Confab → `quote_not_in_chunk` (test green); must_abstain → 0 claims (test green). |
| 4 | Per-CLI conformance (SC3): the @skipUnless test feeds fixtures through the shipped Python gate; trust path is ONLY the Python gate + shell search (no CLI-native tooling) | ✓ VERIFIED | `test_document_agents.py` 16/16 pass — incl. `@skipUnless(corpus/index.db)` `TestDocumentAgentsConformance` driving `grounding.run_eval`/`check_answer` + `searchindex.resolve`. Contract explicitly disclaims MCP/per-CLI plugins; no CLI-native code in trust path. |
| 5 | Employment reference-letter agent (SC4): per-element verbatim quotes cite `#019` (work-experience, not job-offer `#034/#000`); no PII in `claims[].text`; employment fixture grounds `verdict:"pass"` | ✓ VERIFIED | `employment-reference-letter.md` (184 lines) emits one generic claim per element; explicit "Do not confuse with the arranged-employment job-offer letter" guard (`test_employment_guards_against_job_offer_letter` green). Fixture: 4 claims all cite `…completeness-check.md#019`; `#019` resolves to the work-experience completeness-check chunk. `check_answer`→`pass`, `grounded≥4`. Claim text is generic labels (no employer/salary/date literals). |
| 6 | PII boundary: no `police-certificates/<country>` citation, no `/home/`,`/Users/`,`pr-ai-venv` markers in fixture; frozen CONTRACT (`schema_version "1.0"`, exit codes) unchanged; AGENTS.md / copilot-instructions.md GSD blocks not clobbered | ✓ VERIFIED | Fixture: `police-certificates/` count 0; 0 machine-path markers. `crawler/CONTRACT.md` `schema_version "1.0"` + exit-code table present and untouched by phase 27 (git). GSD config blocks intact in `AGENTS.md` and `.github/copilot-instructions.md`; last modified pre-phase-27 (commits `d0c4ef6`/`f4e8804`). | <!-- # publish-safe: allow -->
| 7 | Full suite green except the known pre-existing `test_dupaudit::TestRealCorpus` | ✓ VERIFIED | Per-file run (bounded): checklist 72✓, cli 6✓, document_agents 16✓, dupclean 18✓, engine_refactor 6+26✓, grounding 46✓, json_contract 26✓(+1 skip), parity_ircc 6+30✓, profile_loader 15+3✓, searchindex 59✓, template_profile 4✓; dupaudit 25✓ + `TestRealCorpus` deselected (the documented `result.exact==0` failure, logged in `25/deferred-items.md`). |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `skills/document-agents/_contract.md` | Shared answer-object schema + loop + abstention/PII rules | ✓ VERIFIED | 226 lines; 5-key schema, loop, 3 fail reasons, abstention, PII-tier, no-inlined-volatile rule, exit-code table. |
| `skills/document-agents/README.md` | Additive, self-contained skill-pack index | ✓ VERIFIED | 53 lines; links all 6 agents + `_contract.md`; explicit "Additive only — does not modify GSD-managed AGENTS.md / copilot-instructions.md blocks". |
| `skills/document-agents/police-certificate.md` | Police-cert agent w/ `--family guidance` + country-relpath backstop | ✓ VERIFIED | 132 lines; baked query `police certificate every country`, two-layer no-leak backstop, mirrors `_is_country_specific`. |
| `skills/document-agents/language-test.md` | Approved-test agent | ✓ VERIFIED | 96 lines; baked query `language test approved results`. |
| `skills/document-agents/eca.md` | ECA agent | ✓ VERIFIED | 102 lines; baked query `foreign educational credential assessment`; curly-apostrophe (U+2019) copy hazard documented. |
| `skills/document-agents/proof-of-funds.md` | Settlement-funds agent (figure quoted, never inlined) | ✓ VERIFIED | 124 lines; baked query `proof settlement funds`; no `$N` inlined. |
| `skills/document-agents/medical.md` | IME agent (volatile date quoted from corpus) | ✓ VERIFIED | 134 lines; baked query `immigration medical examination permanent residence`; body inlines no year — date rides in the runtime-quoted span only. |
| `skills/document-agents/employment-reference-letter.md` | Work-experience letter agent (SC4) | ✓ VERIFIED | 184 lines; per-element verbatim-quote loop, job-offer guard, PII-discipline section. |
| `crawler/eval/document_agents.jsonl` | 6 agent answers + confab + must_abstain | ✓ VERIFIED | 8 records; PII-free self-scan green; no `police-certificates/`; confab cites real `#019` w/ absent quote; must_abstain has 0 claims. |
| `crawler/tests/test_document_agents.py` | CHK-03 conformance harness + static grep gate | ✓ VERIFIED | 357 lines; `skipUnless` real-corpus class + always-on fixture-structure/publish-safety/static-gate classes; 16/16 pass. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `_contract.md` | `crawler/grounding.py` answer object | documents `{question,claims[],basis[],abstentions[],prose}` | ✓ WIRED | 5-key schema documented matching the shipped gate. |
| `_contract.md` | `corpus-crawler --json ground` | names the trust-boundary verb | ✓ WIRED | `ground` verb + pass-rule/fail-reasons documented. |
| 6 agents | `corpus-crawler --json search` | baked short queries | ✓ WIRED | Every agent bakes a 2–4-token query + worked search example. |
| `employment-reference-letter.md` | `…completeness-check.md#019` (via query) | baked query `reference letter company letterhead` | ✓ WIRED | Fixture grounds 4 element claims to `#019`; chunk resolves to work-experience completeness-check. |
| `test_document_agents.py` | `crawler.grounding.run_eval`/`check_answer` | feeds fixture through shipped gate | ✓ WIRED | `run_eval` failed==0, code 0; per-line `check_answer` assertions green. |
| `test_document_agents.py` | `scripts/check_publish_safe.scan_text` | publish-safe scan over rendered bytes only | ✓ WIRED | `_load_cps()` + `scan_text` on rendered output and tracked fixture; no whole-tree scan. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Fixture grounds clean through shipped gate | `crawler.cli --json ground --eval crawler/eval/document_agents.jsonl --db corpus/index.db` | `ok:true, total 8, passed 8, failed 0`, exit 0 | ✓ PASS |
| Conformance harness | `pytest crawler/tests/test_document_agents.py -q` | 16 passed | ✓ PASS |
| Volatile date quoted-not-inlined (medical, hardest case) | resolve `medical/…#000`; check substring + body | quote verbatim-in-chunk: True; `2029` in `medical.md`: False | ✓ PASS |
| #019 is work-experience letter (not job-offer) | resolve `…completeness-check.md#019` | found True; relpath = completeness-check; text = work-experience checklist | ✓ PASS |
| Full per-file suite (regression) | `pytest <each file>` bounded | all green except documented `TestRealCorpus` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| CHK-03 | 27-01..27-05 (all 5) | Portable, CLI-agnostic document agents consume the `search` contract, emitting only cited claims (subject to GND-02) | ✓ SATISFIED | All 4 roadmap SCs verified; `run_eval` 8/8; 16/16 conformance tests. (REQUIREMENTS.md tracker still reads "Pending" — a status-flip is the only outstanding bookkeeping; implementation fully fulfills the requirement.) |

No orphaned requirements — CHK-03 is the sole requirement mapped to Phase 27 and is declared in every plan's frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No `TBD`/`FIXME`/`XXX`/`HACK`/`PLACEHOLDER` debt markers in any phase-27 file | ℹ️ Info | None — clean. The "placeholder token" prose in `_contract.md`/`employment-reference-letter.md` describes intentional worked-example tokens (`<relpath#NNN>`, `<employer>`), not stubs. |

### Human Verification Required

None. By design the phase makes cross-CLI conformance a **static/structural** property (plain Markdown, no per-CLI tooling, the entire trust path is the Python gate + shell `search`) and a **machine-verifiable** one (the same fixture passing the same shipped gate). Both were executed and pass, so no runtime multi-CLI human check is required to establish the goal.

### Gaps Summary

No gaps. Every roadmap Success Criterion (SC1–SC4) and every plan `must_haves` truth is backed by codebase evidence plus executed behavior:

- **SC1** — six thin no-front-matter agents over one `_contract.md`, baked queries (no chunk_ids), search→quote→ground loop: VERIFIED by static gate + independent greps.
- **SC2** — only cited claims, zero-claim abstention, gate refuses ungrounded output: VERIFIED by `run_eval` (confab fails closed `quote_not_in_chunk`; must_abstain passes with 0 claims).
- **SC3** — per-CLI conformance with no CLI-native tooling in the trust path: VERIFIED by the @skipUnless harness driving the shipped Python gate; same fixture + same gate is the conformance proof.
- **SC4** — employment letter verifies work-experience elements via per-element cited quotes to `#019` (not the job-offer), PII-free, grounds `pass`: VERIFIED.

Frozen primitives (CONTRACT `schema_version "1.0"` + exit codes, `grounding.py`, `searchindex.py`, `checklist.py`, `dupaudit.py`) and GSD config blocks (`AGENTS.md`, `.github/copilot-instructions.md`) are untouched by this phase. The only full-suite red is the pre-existing, documented `test_dupaudit::TestRealCorpus` (`result.exact==0`), explicitly logged as out-of-scope in `25/deferred-items.md` and unrelated to Phase 27 (which modified no `crawler/` product code).

---

_Verified: 2026-06-21T14:55:46Z_
_Verifier: the agent (gsd-verifier)_
