# Phase 27 — CLI-Agnostic Document Agents · Validation Strategy (Nyquist)

**Requirement:** CHK-03 (portable, CLI-agnostic document agents consume the `search` contract, emit only cited claims, gated by GND-02)
**Goal under test:** Six portable plain-Markdown document-agent skills (police certificate, language test,
ECA, proof of funds, medical, employment reference letter) answer document questions by consuming the
`search` contract and emitting only gated, cited claims — identically across CLIs.

This file is the **sampling plan**. Because Phase 27 ships NO trust-path code (it is an
authoring/integration phase over the frozen Phase-24 `search` → Phase-25 `ground` pipeline), the Nyquist
probes are of two kinds: (a) **static grep gates** over the plain-Markdown skills (no proprietary
front-matter, no bare `python`, no inlined volatile requirement values, links to the shared `_contract.md`,
bakes a `search` query not a chunk_id) and (b) one **behavioral conformance harness** that feeds every
agent's example answer through the shipped Python gate and asserts `verdict:"pass"` with the expected
deterministic citation set — which IS the per-CLI conformance proof (the entire trust path is the Python
gate + shell `search`, identical regardless of which CLI drove the agent). **Bare `python` is broken
(Windows pyenv-win CRLF / `/bin/sh^M`); every command runs through `.venv/bin/python` or the
`corpus-crawler` console script.**

---

## Success-criterion → validation map

| SC (CHK-03) | What must be TRUE | Validating check(s) | Plan |
|-------------|-------------------|---------------------|------|
| **SC1** Six thin plain-MD skills share one `_contract.md`; retrieve via `--json search`, copy a verbatim `quote`, pipe to `--json ground` | each skill exists, has NO `---` front-matter, links `_contract.md`, names `json search`+`json ground`, bakes a query (not a `#NNN` chunk_id) | grep gates per skill (front-matter, `_contract.md` link, `json search`/`json ground`, no `#[0-9]{3}`) | 01, 02, 03, 04 |
| **SC2** Only cited claims; abstain ("not in corpus") when no answer; gate refuses ungrounded | `_contract.md` documents the 5-key answer object + the three fail reasons (`uncited`/`unresolvable`/`quote_not_in_chunk`) + the abstention rule; the conformance fixture includes an adversarial `confab` (expect ungrounded → gate fails) and a `must_abstain` line | `_contract.md` grep gates; `run_eval` over `document_agents.jsonl` (confab line fails closed, abstain line passes) | 01, 05 |
| **SC3** Per-CLI conformance: same question → same resolved citation set passes the gate; no CLI-native tooling in the trust path | the `@skipUnless(corpus/index.db)` conformance test feeds all six example answers through `corpus-crawler --json ground --eval` and asserts `verdict:"pass"` + the deterministic citation set — identical across CLIs because the trust path is only the Python gate + shell `search` | `test_document_agents.py` (real-corpus `run_eval`, `failed==0`) | 05 |
| **SC4** Employment reference letter agent verifies the required elements, each gated + cited, no PII in `claims[].text` | `employment-reference-letter.md` cites the proof-of-work-experience chunk `pr-pdi/...completeness-check.md#019` (NOT the job-offer #034/#000) for each element via per-element verbatim quotes; the fixture's employment line grounds `verdict:"pass"` over `#019`; no PII (employer/dates/salary) in `claims[].text` | `employment-reference-letter.md` grep gates (no front-matter, links contract, no inlined values); the `employment` fixture line in the conformance run | 04, 05 |

---

## The validation strands

### 1. No-confabulation / grounding-by-construction — the headline (SC2/SC3, CHK-03)
- **Behavioral (real-corpus harness):** `crawler/tests/test_document_agents.py` (`@skipUnless(corpus/index.db)`) feeds `crawler/eval/document_agents.jsonl` through the SHIPPED Phase-25 gate
  (`grounding.run_eval` / `corpus-crawler --json ground --eval`). It asserts all six agent example answers
  ground `verdict:"pass"` (`failed==0`), the adversarial `confab` line FAILS closed (`quote_not_in_chunk`),
  and the `must_abstain` line passes by carrying zero claims. This is the per-CLI conformance proof: the
  trust path is entirely the Python gate + shell `search`, so the same fixture passes the same gate under
  Antigravity / Codex / Claude / Copilot.
- **Static:** `_contract.md` grep gates assert it documents the 5-key answer object, the three fail reasons,
  and the abstention rule — so every skill teaches the same fail-closed loop.

### 2. Portable, CLI-agnostic, no-proprietary-format (SC1, CHK-03)
- Per-skill grep gates: `head -1 <skill> | grep -qx -- '---'` must NOT match (no YAML front-matter); each
  skill links `_contract.md`; each names `json search`/`json ground`; none bakes a `#NNN` chunk_id (agents
  retrieve live, they don't hardcode coordinates).
- Pointer-file safety: the additive `skills/document-agents/README.md` lists all six agents and the shared
  contract; `git status --short AGENTS.md .github/copilot-instructions.md` is empty (the GSD-managed root
  files are NOT clobbered).

### 3. No inlined volatile requirement values (SC1/SC4, CHK-03)
- Grep gates assert no skill inlines a dollar amount, validity window, or date (e.g. proof-of-funds has no
  `\$[0-9]`/`[0-9],[0-9]{3}`; the medical agent's IME date `until October 5, 2029` must be QUOTED FROM the
  corpus via a citation, never written into the prose). Every requirement value resolves from `search`.

### 4. PII boundary + no residence/employer leak (SC4, CHK-02 inheritance)
- The police agent uses `--family guidance` + the `police-certificates/<country>` relpath backstop; the
  fixture has no `police-certificates/<country>` citation and no `/home/`,`/Users/`,`pr-ai-venv` markers. <!-- # publish-safe: allow -->
- The employment agent cites only the generic `#019` chunk; no employer name / dates / salary appear in
  `claims[].text` (PII, if any, lives in `basis[]`, which the gate never checks and `render_answer` never
  emits).

### 5. Employment reference letter — the new 6th agent (SC4)
- `employment-reference-letter.md` exists, is front-matter-free, links the contract, and cites `#019` for
  each required element (letterhead, contact, signatory+title, positions, duties, status, dates, hours,
  salary+benefits) via per-element verbatim quotes; a guard note prevents confusing it with the job-offer
  letter (#034/#000). The fixture's `employment` line grounds `verdict:"pass"` over `#019` in strand 1.

---

## Nyquist rate justification

- **Two probe kinds, continuous sampling:** every skill carries a fast static grep gate (front-matter,
  contract link, query-not-chunkid, no-bare-python, no-volatile-values) AND is exercised behaviorally by the
  single real-corpus conformance harness — so neither a malformed skill nor a confabulated/ungrounded claim
  can hide between probes.
- **No watch-mode, no browser/E2E, no network** — grep gates + one `run_eval` invocation finish in seconds;
  the only environment-gated probe is the conformance test, `@skipUnless(corpus/index.db)`.
- **Regression floor:** the conformance harness reuses the frozen `search`/`ground` primitives unchanged, so
  the document agents cannot regress them; `corpus/index.db` (742 docs) is present so the harness RUNS, not
  skips.

## Honesty boundary (inherited)

The agents reuse the Phase-25 gate unchanged: each requirement line is guaranteed resolvable +
verbatim-quoted, NOT semantically entailed (VAL-01/02 deferred). Layer-2 per-document rule matching
(recency/amounts/format/translation) is out of scope for Phase 27 — the agents answer "which elements are
required, each cited", not full Layer-2 validation.
