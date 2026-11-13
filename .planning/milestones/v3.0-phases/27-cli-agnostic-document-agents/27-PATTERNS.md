# Phase 27: CLI-Agnostic Document Agents - Pattern Map

**Mapped:** 2026-06-21
**Files analyzed:** 9–11 new files (6 agent skills + 1 shared contract + 1 conformance harness + 1 fixture set; optional skill-dir README + per-CLI pointer files)
**Analogs found:** 9 / 9 (every artifact has a strong in-repo analog)

> This phase is **mostly plain-Markdown agent skills + a conformance harness**, NOT new
> trust-path Python. The Python primitives the agents shell out to (`search`, `ground`,
> `checklist`) already ship (Phases 24/25/26). The skills' job is to TEACH an agent — in
> portable prose + shell — to replicate the *behaviour* already implemented deterministically
> in `crawler/checklist.py`. So most "code to copy" here is **structure/tone/shell-invocation
> patterns** from `crawler/AGENT_SKILL.md`, plus the **answer-object schema** and the
> **search→resolve→verbatim-quote→ground loop**, NOT Python re-implementation.

---

## File Classification

| New/Modified File (proposed) | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `<skills-dir>/police-certificate.md` | skill (agent-prompt, plain MD) | request-response (search→ground) | `crawler/AGENT_SKILL.md` | exact (same genre) |
| `<skills-dir>/language-test.md` | skill | request-response | `crawler/AGENT_SKILL.md` | exact |
| `<skills-dir>/eca.md` | skill | request-response | `crawler/AGENT_SKILL.md` | exact |
| `<skills-dir>/proof-of-funds.md` | skill | request-response | `crawler/AGENT_SKILL.md` | exact |
| `<skills-dir>/medical.md` | skill | request-response | `crawler/AGENT_SKILL.md` | exact |
| `<skills-dir>/employment-reference-letter.md` | skill (NEW 6th doc type) | request-response | `crawler/AGENT_SKILL.md` | exact (genre); corpus content distributed — see *No Analog* |
| `<skills-dir>/_contract.md` (shared) | contract/doc | schema reference | `crawler/CONTRACT.md` + `crawler/grounding.py:1-43` docstring | exact |
| conformance harness (`crawler/tests/test_doc_agents.py` *or* `scripts/conformance.*`) | test / gate-over-fixtures | request-response + batch | `crawler/tests/test_grounding.py` (`TestGroundCli`) + `grounding.run_eval` + `crawler/eval_runner.py` | role-match |
| conformance fixture set (`<...>/questions.jsonl`-style) | test fixture | data | `crawler/eval/questions.jsonl` | exact |
| `<skills-dir>/README.md` (optional index) | doc | n/a | `crawler/README.md:205-212` (the AGENT_SKILL pointer) | partial |
| per-CLI pointer files (`CLAUDE.md` / `.github/copilot-instructions.md`, optional) | config/pointer | n/a | `AGENTS.md` (GSD pointer convention) | partial |

**Behaviour reference (not a file the agent writes, but the implementation the skills must
mirror in prose):** `crawler/checklist.py` — the Phase-26 PRODUCER that already does
applicability→`basis[]`, gated PII-free `claims[]`, generic citations, the
search→resolve→verbatim-quote loop, the country-relpath backstop, and demote-ungroundable-to-abstention.

---

## Pattern Assignments

### The six document-agent skills (skill, request-response) — `<skills-dir>/<doc-type>.md`

**Analog:** `crawler/AGENT_SKILL.md` (172 lines — read in full).

This is THE template. Copy its **structure, tone, and portability framing verbatim**, then
narrow scope from "drive the whole pipeline" to "answer one document type's questions via
`search` → emit a gated, cited answer → pipe through `ground`."

**Portability framing to copy** (`crawler/AGENT_SKILL.md:1-11`) — open every skill with this:
```markdown
A **portable, CLI-agnostic** skill. It is plain Markdown with no proprietary
front-matter and no dependency on any single agent CLI's tool API. Any agent —
Antigravity, OpenAI Codex, Claude, GitHub Copilot, Gemini, or a plain shell
script — can use it, because everything here is **an ordinary shell command plus
JSON parsing**.
```
Locked anchor from CONTEXT (decisions): NO proprietary front-matter, NO per-CLI tool/MCP API —
every step is `corpus-crawler --json search` / `--json ground` + JSON parsing. This opener
encodes exactly that.

**Pointer to the shared contract** — mirror `crawler/AGENT_SKILL.md:9-11` which points at
`CONTRACT.md`; each doc-agent skill instead points at the shared `_contract.md`:
```markdown
The structured answer object every document agent emits (the schema, every field,
the abstention rule) lives in [`_contract.md`](_contract.md). This skill teaches you
how to *use* that contract for <doc type> questions.
```

**The `--json <verb>` invocation invariant to copy** (`crawler/AGENT_SKILL.md:22-39`):
```markdown
Invoke `corpus-crawler` as an ordinary shell command. To get a machine-readable
result, add the **global `--json` flag before the subcommand**:

    corpus-crawler --json <subcommand> [args...]

- **stdout** is exactly **one JSON object** — capture it and `json.loads` it.
- **stderr** is human/progress/log text — surface it as diagnostics; never parse it.
```

**The five-key envelope + read-`ok`-first rule to copy** (`crawler/AGENT_SKILL.md:41-55`):
```markdown
Read `ok` first. If `ok` is `true`, read `result`. If `ok` is `false`, read
`error.type` and `error.message`.
```

**Worked-example shape to copy** (`crawler/AGENT_SKILL.md:91-100`) — the skill teaches the
agent the *loop* with a runnable shell example. ⚠️ See **Decision point 5 (bare python)**: the
analog pipes into bare `python -c`, which is BROKEN in this repo — use `.venv/bin/python` (or
the `corpus-crawler` console-script everywhere) in the skill examples.

**Per-skill core loop the markdown must teach** (this is the search→resolve→verbatim-quote→ground
producer pattern, drawn from `crawler/checklist.py:339-388` `grounded_claim`):
1. Read the local profile slice for applicability → goes to `basis[]` (PII), never `claims[].text`.
2. For each requirement, run `corpus-crawler --json search "<2-4 token query>"` (do NOT inline
   the requirement value — Decision/anchor: no hardcoded volatile values).
3. Resolve the chosen hit verbatim: `corpus-crawler --json search --cite "<chunk_id>"` → take
   `result.chunk.text` (the exact quotable span; the `snippet` is display-only — `CONTRACT.md:200-205`).
4. Copy a VERBATIM substring of that `text` into `quote`.
5. Assemble the answer object (see `_contract.md`); pipe to `corpus-crawler --json ground`.
6. If no resolving generic hit exists → emit an `abstention` ("not in corpus"), NEVER a claim.

**Exit-code table to copy** (`crawler/AGENT_SKILL.md:153-165`) — the same 0/1/2/3/4 taxonomy.

---

### Shared `_contract.md` (contract/doc) — `<skills-dir>/_contract.md`

**Analog:** `crawler/CONTRACT.md` (structure/tone) + the answer-object docstring in
`crawler/grounding.py:1-43` (the canonical shape) + the live example in
`crawler/eval/questions.jsonl`.

This is the ONE shared contract all six agents reference (locked anchor). It must define the
structured answer object exactly as the Phase-25 gate expects.

**Answer-object schema to document** (verbatim from `crawler/grounding.py:4-12`):
```python
{
    "question":   str,
    "claims":     [{"id": str, "text": str, "citations": [str, ...], "quote": str}],
    "basis":      [...],   # free-form supporting material — NEVER citation-checked
    "abstentions":[...],   # declared non-answers       — NEVER citation-checked
    "prose":      str,     # human-readable narration    — NEVER citation-checked
}
```
Critical contract facts to spell out (from `grounding.py`):
- The gate inspects **`claims[]` ONLY** — `basis`/`abstentions`/`prose` are never citation-checked
  (`grounding.py:185-215`, `check_answer`). This is what makes PII-in-`basis[]` safe.
- A claim passes iff **≥1 citation BOTH resolves AND the verbatim `quote` is a
  whitespace/case-normalized substring** of that chunk (`grounding.py:102-146`, `check_claim`).
- Fail reasons are exactly `uncited` / `unresolvable` / `quote_not_in_chunk`
  (`grounding.py:105-113`).
- Every claim MUST carry all of `id`/`text`/`citations`/`quote`; a missing key or a
  **non-string `quote`** is `invalid_input`/exit 2, NOT a soft fail (`grounding.py:56`, `149-182`).
- Quote normalization is `re.sub(r"\s+", " ", s).strip().lower()` and NOTHING else
  (`grounding.py:78-84`) — agents may differ in whitespace/case but not otherwise.

**Live answer example to embed** (a real grounded line, `crawler/eval/questions.jsonl:2`):
```json
{"id":"medical-ime-who-01","expect":"grounded","question":"Who must undergo an immigration medical examination for permanent residence?","claims":[{"id":"c1","text":"Foreign nationals applying for a permanent resident visa, or applying to remain in Canada as a permanent resident, must undergo an immigration medical examination.","citations":["medical/who-must-submit-immigration-medical-examination.md#000"],"quote":"Foreign nationals who are applying for a permanent resident visa (PRV) or applying to remain in Canada as a permanent resident"}],"basis":[],"abstentions":[],"prose":""}
```

**Abstention example to embed** (`crawler/eval/questions.jsonl:3`) — the "not in corpus" rule:
```json
{"id":"adversarial-lunar-residency-01","must_abstain":true,"question":"What is the application fee for a Lunar Gateway residency permit?","claims":[],"basis":[],"abstentions":[{"text":"A Lunar Gateway residency permit is not an IRCC program; there is no such fee in the corpus.","reason":"not_in_corpus"}],"prose":""}
```

**`search --cite` resolve schema to document** (`crawler/CONTRACT.md:194-205`) — how the agent
gets the verbatim quote span:
```markdown
**Citation resolve** (`search --cite <id>`): result.found / result.chunk.
On a hit, `chunk` has chunk_id, relpath, source_url, title, section, crawl_date, and
`text` — the EXACT verbatim chunk text (the quotable span; NOT the `snippet`).
```

---

### Conformance harness (test / gate-over-fixtures)

**Decision point 4** governs its *form* (pytest test vs. standalone script). Both have analogs:

**Analog A — `crawler/eval/questions.jsonl` + `grounding.run_eval` (the "gate IS the eval" idea).**
The cleanest portable conformance proof: a fixture set of complete answer objects, run through
the SAME `corpus-crawler --json ground --eval <questions.jsonl>` gate. From `grounding.py:218-311`
(`run_eval`): one stored answer per JSONL line; optional `expect` marker
(`"grounded"`/`"ungrounded"`) and `must_abstain`; returns `{total, passed, failed, failures}`,
exit 1 if ANY line fails. The eval mode is already wired into the `ground` verb
(`crawler/cli.py:480-498`, checked BEFORE any stdin read). This is the "one grounded question →
verified citation set passes the gate identically across CLIs" proof — because the trust path is
the shared Python gate, the SAME fixture passes regardless of which CLI produced it.

**Fixture pattern to copy** (`crawler/eval/questions.jsonl:1` — grounded; line 5 — adversarial
`expect:"ungrounded"` to positively test fail-closed):
```json
{"id":"police-cert-ideco-01","expect":"grounded","question":"Are Ideco Biometrics certificates accepted for immigration purposes?","claims":[{"id":"c1","text":"Ideco Biometrics certificates are not valid for immigration purposes; applicants should request the standard Republic of South Africa police clearance certificate.","citations":["police-certificates/south-africa.md#005"],"quote":"Certificates from Ideco Biometrics are **not** valid for immigration purposes."}],"basis":[],"abstentions":[],"prose":""}
{"id":"adversarial-fabricated-citation-01","expect":"ungrounded","question":"...","claims":[{"id":"c1","text":"...","citations":["synthetic-nonexistent/atlantis-settlement-fee.md#999"],"quote":"..."}],"basis":[],"abstentions":[],"prose":""}
```

**Analog B — `crawler/tests/test_grounding.py` `TestGroundCli` (end-to-end through `cli.main`).**
If the harness is a pytest test, copy these conventions (from `test_grounding.py:1-27`, `46-72`):
- Stdlib `unittest` ONLY — no pytest fixtures, no network, no browser (house rule / AGENTS.md).
- Build a SYNTHETIC tiny corpus in a `tempfile.TemporaryDirectory` via `searchindex.build_index`;
  NEVER touch the real git-ignored `corpus/` (`test_grounding.py:50-57`).
- Drive the verb through `cli.main([...])` capturing exit code + stdout/stderr, assert
  one-line pure-JSON envelope + `ok`/`verdict`/exit (`test_checklist.py:811-823`, `829-848`).
- Run command (note the venv): `.venv/bin/python -m pytest crawler/tests/test_<name>.py -q`
  (`test_grounding.py:12`).

**Analog C — `crawler/eval_runner.py` (standalone runner shape).** If the harness is a script,
copy its `{total, passed, failed, failures}` summary shape and `1 if failed else 0` exit
(`eval_runner.py:134-150`) — `grounding.run_eval` already mirrors this exact shape on purpose
(`grounding.py:244-246`).

**End-to-end shell-out conformance via the console script** (`crawler/tests/test_checklist.py:1156-1161`):
```python
out = subprocess.run(
    ["git", "-C", str(_REPO_ROOT), *args],
    check=True, capture_output=True, text=True,
)
```
Adapt this `subprocess.run([...])` shape to invoke `corpus-crawler --json ground --eval <fixtures>`
(or `.venv/bin/python -m crawler.cli ...`) and assert identical `result`/exit across runs.

---

## Shared Patterns

### 1. Portable shell + one-JSON-object invariant
**Source:** `crawler/AGENT_SKILL.md:22-55`
**Apply to:** all six skills + `_contract.md`
Every interaction is `corpus-crawler --json <verb>` → stdout is exactly one JSON object → read
`ok` first. No proprietary tooling, MCP, or per-CLI plugin. This single invariant is *what makes
the agents CLI-agnostic* and is the root of the conformance guarantee.

### 2. The structured answer object (the 5-key contract)
**Source:** `crawler/grounding.py:1-43`, `56`, `102-215`; live in `crawler/eval/questions.jsonl`
**Apply to:** `_contract.md` (defines it) + all six skills (emit it)
`{question, claims:[{id,text,citations[],quote}], basis[], abstentions[], prose}`. Gate checks
`claims[]` ONLY. ≥1 citation must resolve AND contain the verbatim quote substring.

### 3. Grounding-by-construction: search→resolve→verbatim-quote→ground (PRODUCER loop)
**Source:** `crawler/checklist.py:339-388` (`grounded_claim`), `402-456` (`build_answer`)
**Apply to:** all six skills (teach this loop in prose+shell)
- `search` with a SHORT 2-4 high-signal-token generic query (`checklist.py:339-360`).
- Slice a VERBATIM span from the resolved chunk `text`; demand a minimally meaningful span
  (degenerate quotes fail closed → abstain) (`checklist.py:315-336`, `_verbatim_quote`).
- Assemble, run THROUGH `ground`, and **demote any gate-rejected claim to an explicit
  abstention** so the emitted answer always verifies `pass` (`checklist.py:434-456`).
- Honesty boundary: never an empty, claimless, abstention-less answer (`checklist.py:450-455`).

### 4. PII boundary — `basis[]` vs `claims[].text` (CHK-02 inheritance)
**Source:** `crawler/checklist.py:131-268` (`applicable_items`), `391-399` (`_assemble_answer`)
**Apply to:** all six skills, especially employment-reference-letter
- Generic, PII-FREE requirement label → `claims[].text` (NEVER interpolates a profile value).
- The applicability/personalization reason (countries, dates, counts, employer name, salary) →
  `basis[]` ONLY (`checklist.py:141-145`, the locked PII-tier split).
- Country-/employer-specific **relpath backstop**: NEVER cite a chunk whose path leaks PII;
  skip to the next generic hit, else abstain (`checklist.py:290-312`, `339-388`,
  `_COUNTRY_SPECIFIC_FAMILIES = ("police-certificates/",)`). The employment agent needs the
  analogous rule for any per-employer/per-applicant path.
- No hardcoded volatile values (dollar amounts, validity windows, requirement text) — every
  requirement statement comes from `search` with a citation (CONTEXT decisions; "grep finds no
  inlined volatile values" rule).

### 5. Abstention rule ("not in corpus")
**Source:** `crawler/grounding.py:228-264` (`run_eval` `must_abstain`); `crawler/eval/questions.jsonl:3-4`
**Apply to:** all six skills + `_contract.md` + conformance fixtures
When the corpus has no answer: emit ZERO claims + an explicit `abstention` with `reason:"not_in_corpus"`.
The gate treats a must-abstain answer that smuggles any claim as a failure (`should_have_abstained`).

### 6. Test/harness conventions
**Source:** `crawler/tests/test_grounding.py:1-27`, `test_checklist.py:1-23`; AGENTS.md house rule
**Apply to:** the conformance harness
Stdlib `unittest` only (no pytest fixtures/network/browser); synthetic tempdir corpus, never the
real `corpus/`; drive through `cli.main` or `subprocess`; assert one-line pure-JSON envelope.
**Run via `.venv/bin/python`** (Decision point 5).

### 7. Skill-directory pointer convention
**Source:** `crawler/README.md:205-212`, `crawler/CONTRACT.md:399`, `AGENTS.md`
**Apply to:** optional README/index + optional per-CLI pointer files
Existing pattern: `README.md`/`CONTRACT.md` cross-link to `AGENT_SKILL.md` as "the portable,
CLI-agnostic agent skill." Mirror this so the six skills + `_contract.md` are discoverable; thin
per-CLI files (CLAUDE.md / copilot-instructions.md) should only REDIRECT to the canonical skills.

---

## No Analog Found

| File / concern | Role | Data Flow | Reason / Flag for planner |
|---|---|---|---|
| `employment-reference-letter.md` (the 6th, NEW doc type) | skill | request-response | The *skill genre* analog is `AGENT_SKILL.md` (exact), and the *producer behaviour* analog is `checklist.py`. BUT there is **no single corpus page** listing the Express-Entry reference-letter required elements; the elements are **distributed** across `corpus/guidance/federal-skilled-workers.md` (`main duties`, `1,560 hours / 30 hours per week`), `corpus/guidance/canadian-experience-class.md`, `corpus/guidance/apply-permanent-residence.md` (`name and signature`, `hand/digital signature`), and the `corpus/pr-pdi/economic-classes-federal-skilled-workers-arranged-employment*.md` family. **Flag:** each element statement must `search`→cite its OWN chunk; some elements (company letterhead/contact, signatory title, annual salary + benefits) may not be groundable in the current corpus → those must ABSTAIN, not be hardcoded. Researcher/planner should confirm corpus coverage per element. |
| skills directory itself | n/a | n/a | **No existing `agents/` or `skills/document-agents/` dir** (`find` returned nothing). Greenfield — see Decision point 1. |
| per-CLI pointer files (CLAUDE.md / `.github/copilot-instructions.md`) | config | n/a | Closest pattern is `AGENTS.md` (GSD pointer), but no doc-agent pointer exists yet. Optional — see Decision point 6. |

---

## Decision Points for the Planner

1. **Skill directory location.** No existing dir. Options: top-level `agents/`, `skills/document-agents/`,
   or under `crawler/` beside `AGENT_SKILL.md`. The existing convention keeps the portable skill
   inside `crawler/` (next to `CONTRACT.md`/`README.md` it points to), so `crawler/`-adjacent or a
   sibling top-level `agents/` both fit. Pick one and place `_contract.md` there as the shared root.
2. **How the six agents share `_contract.md`.** Locked anchor = ONE shared contract. Recommended:
   `_contract.md` holds the answer-object schema + the search→quote→ground loop + the abstention
   rule (the parts identical across agents); each `<doc-type>.md` stays THIN — only the doc-specific
   queries/requirements + a link to `_contract.md` (mirrors how `AGENT_SKILL.md` defers the schema
   to `CONTRACT.md`).
3. **Employment-reference-letter element list.** Do NOT hardcode the elements (anchor: no inlined
   requirement text). Each required element (letterhead/contact, signatory + title, job title(s),
   employment dates/period, hours/full-time status, annual salary + benefits, detailed duties) must
   be a `search`-and-cite step; ungroundable elements ABSTAIN. Confirm corpus coverage (see *No
   Analog*) before finalizing the element set.
4. **Conformance harness form.** Three viable shapes (all with analogs): (A) a
   `questions.jsonl`-style fixture run through `corpus-crawler --json ground --eval` (leanest,
   most portable — reuses `grounding.run_eval`); (B) a `crawler/tests/test_doc_agents.py` pytest
   suite driving `cli.main`/`subprocess` (matches `test_grounding.py`/`test_checklist.py`); (C) a
   standalone `scripts/` runner (matches `eval_runner.py`). (A) most directly proves "same question
   → same resolved citation set passes identically across CLIs." Recommend A, optionally wrapped by B.
5. **⚠️ CRITICAL ENV — bare `python` is broken.** `crawler/AGENT_SKILL.md`'s worked examples pipe
   into bare `python -c` (`:98, :111, :133, :142`). In THIS repo bare `python` is broken — any
   harness command/test MUST use `.venv/bin/python` (e.g. `.venv/bin/python -m pytest …`,
   `.venv/bin/python -m crawler.cli …`). Decide the portable guidance for the skills' shell
   examples: prefer the `corpus-crawler` console-script (`pyproject.toml:21-22`) for the verb and
   `.venv/bin/python` (or `jq`) for JSON parsing, and note the bare-python caveat.
6. **Per-CLI pointer files (optional).** Whether to ship thin `CLAUDE.md` /
   `.github/copilot-instructions.md` that redirect to the canonical skills, or rely on the skills
   being plain Markdown any CLI can read directly. If shipped, they must ONLY redirect (no logic) —
   the trust path stays the Python gate + shell `search`.

---

## Metadata

**Analog search scope:** `crawler/` (skill, contract, grounding gate, checklist producer, eval
runner, CLI verbs, tests), `crawler/eval/`, `crawler/tests/`, `corpus/` (groundability spot-check),
repo root (`AGENTS.md`, `.gitignore`, `pyproject.toml`), `.planning/`.
**Files scanned:** `crawler/AGENT_SKILL.md`, `crawler/CONTRACT.md`, `crawler/grounding.py`,
`crawler/checklist.py`, `crawler/cli.py`, `crawler/eval_runner.py`, `crawler/eval/questions.jsonl`,
`crawler/tests/test_grounding.py`, `crawler/tests/test_checklist.py`, `AGENTS.md`, `.gitignore`,
`pyproject.toml`, plus `corpus/` greps.
**Key primitives confirmed shipped (no trust-path code needed):** `corpus-crawler --json search`
(+`--cite`), `--json ground` (+`--eval`), `--json checklist` — frozen 5-key envelope,
schema_version "1.0", exit-code taxonomy 0/1/2/3/4.
**Pattern extraction date:** 2026-06-21
