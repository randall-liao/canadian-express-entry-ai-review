# Phase 26: Personalized Layer-1 Checklist + PII Separation - Research

**Researched:** 2026-06-21
**Domain:** Personalized document-checklist generation that reuses the Phase-25 grounding gate, with a hard PII-separation boundary (local profile → gated, cited claims → git-ignored rendered output)
**Confidence:** HIGH (the gate, retrieval, scan, and PII boundary are all shipped and were exercised end-to-end this session; the profile schema is a design proposal grounded in the corpus document list)

## Summary

Phase 26 adds a **producer**: a `checklist` generator that reads a LOCAL `profile.yaml`, decides which Layer-1 ("which documents you need") items apply to a post-ITA Express Entry applicant, retrieves the *generic* requirement text + verbatim quote for each applicable item from the corpus, assembles a Phase-25 answer object, and runs it through the already-shipped grounding gate. Nothing in the trust path is new machinery — `grounding.check_answer` / `render_answer` (Phase 25), `searchindex.search` / `resolve` (Phase 24), `check_publish_safe.scan_text` + `CORPORA_PREFIXES` (RPT-03), and `contract.envelope` / `EXIT_*` are all reused. The only new code is the profile reader + applicability mapper + a thin CLI verb. Constraint is absolute: **stdlib + PyYAML only, no new deps** (PyYAML 6.0.3 is already declared and was verified importable).

The phase's defining idea is a **separation of two PII tiers**. The *requirement text + citation* is generic, public, PII-free, and comes from the corpus — it is gated. The *applicability* (which countries you lived in since 18, your stream, your education claim) is PII — it decides **which** claims are included and is recorded only in `basis[]`, which the gate never checks and `render_answer` never renders. Because `render_answer` emits only `claims[].text` + verbatim quote + citation (never `basis[]`), the rendered checklist is PII-free *by construction*; the RPT-03 scan over the rendered bytes is the fail-closed secondary guard. I drove this end-to-end this session: a checklist-shaped answer (PII-free police-certificate claim citing `guidance/police-certificates.md#002`, applicability in `basis[]`) passed the `ground` verb with `verdict:"pass"` and rendered cleanly under `personal/output/`.

The single biggest design subtlety is **citation choice**: citing a country-specific page (e.g. `police-certificates/south-africa.md`) leaks the user's residence history through the relpath in the rendered output. The recommendation is to cite the **generic rule pages** (`guidance/police-certificates.md`, etc.) for the requirement and keep all per-country specifics in `basis[]`/local. This keeps the gated, rendered, scanned artifact PII-free and makes the self-test (no sentinel PII token appears in `claims[].text` or rendered bytes) clean.

**Primary recommendation:** Build `crawler/checklist.py` (pure: `load_profile` via `yaml.safe_load` → `applicable_items(profile)` → per item: short targeted `searchindex.search` → `resolve` top hit → extract a **verbatim** quote span from the live chunk → build a PII-free `claim`) + a thin `checklist` CLI verb that assembles the answer object, runs `grounding.check_answer`, then reuses the exact `_cmd_ground` render→scan→write-to-`personal/output/` path. Cite **generic** corpus rule pages; put all PII in `basis[]`; drive tests from a synthetic `personal.example/profile.yaml` carrying sentinel fake PII.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHK-01 | Generate a personalized Layer-1 document checklist for a post-ITA Express Entry applicant from the local profile, every item grounded and cited to the corpus. | Verified end-to-end: a checklist-shaped answer object passes `grounding.check_answer`/`ground` and renders. Profile→applicability mapping table (below) maps each profile field to applicable Layer-1 doc types; each doc type maps to a VERIFIED corpus query→chunk→verbatim quote. The "every requirement line is a gated `claims[]` entry" requirement is satisfied by the producer emitting the Phase-25 answer shape and passing it THROUGH the gate. |
| CHK-02 | All user PII (profile, documents, answers) stays in the local git-ignored area — never the repo or corpus DB. | Verified: `.gitignore` ignores `personal/` + un-ignores `!personal.example/`; `check_publish_safe.CORPORA_PREFIXES` includes `personal/` and `scan_path_name` fails closed on any tracked `personal/` file; `_cmd_ground` anchors output under `<repo>/personal` (CR-03) and runs `scan_text` over rendered bytes before writing. Architecture keeps PII in `basis[]` (never gated, never rendered). Self-test uses sentinel PII in `personal.example/profile.yaml`. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Read `$PR_PERSONAL_DIR/profile.yaml` (PII in) | New `checklist.py` (local/git-ignored data tier) | `yaml.safe_load` | Profile is untrusted local config; parsing must be PII-aware and never construct arbitrary objects. New code (no resolution exists today). |
| Decide WHICH items apply (applicability) | New `checklist.py` pure logic | — | Pure function of profile fields; this is the personalization. Output: which claims to emit + per-item `basis[]` text (PII). NEVER citation-checked. |
| Requirement TEXT + citation (the grounded fact) | Corpus retrieval — `searchindex.search`/`resolve` (Phase 24) | — | Generic, public, PII-free. The verbatim quote is sliced from the live resolved chunk so it grounds by construction. |
| Gate every claim (fail-closed) | `grounding.check_answer` (Phase 25) | `grounding.quote_is_grounded` | The acceptance bar. Reused verbatim; do NOT re-implement resolution or the quote check. |
| Render cited checklist | `grounding.render_answer` (Phase 25) | — | Renders only `claims[].text` + quote + citation; never `basis[]` → rendered bytes are PII-free by construction. |
| Publish-safety scan of rendered bytes | `check_publish_safe.scan_text` (RPT-03) | — | Render-then-scan-then-write; fail-closed refusal (`internal_error`/exit 4) before any write. |
| Confine output to git-ignored `personal/` | `cli._personal_root` + anchored containment (CR-03) | `.gitignore` + `CORPORA_PREFIXES` | Two independent guards: write-time anchored path check, and the tracked-tree scanner that fails closed if `personal/` is ever `git add`-ed. |
| Machine-readable result + exit codes | `contract.envelope` / `EXIT_*` | — | Frozen 5-key envelope, additive new `checklist` command string only. |

## User Constraints (from CONTEXT.md)

### Locked Decisions / Anchors to Honor
- The checklist is a **PRODUCER** that emits the Phase-25 answer object `{question, claims:[{id,text,citations[],quote}], basis[], abstentions[], prose}` and passes it THROUGH the Phase-25 gate (`grounding.check_answer` / the `ground` verb). Requirement text + citation come from the corpus (`searchindex.search`/`resolve`) and are gated; profile-derived applicability goes in `basis[]` and is NEVER citation-checked.
- **HARD PII boundary:** profile (`$PR_PERSONAL_DIR/profile.yaml`, default `./personal/`) and rendered output (`personal/output/`) are git-ignored. The synthetic `personal.example/` is the ONLY tracked profile artifact. `.gitignore` already has `personal/` ignored + `!personal.example/` un-ignored.
- `claims[].text` (the gated requirement statements) must contain **NO PII** — PII (countries, dates, names) lives only in `basis[]` / local files, never in gated claim text or the corpus DB.
- **Reuse**: `grounding` (gate + render-then-scan), `searchindex.search`/`resolve` (Phase 24), `check_publish_safe.scan_text`/`CORPORA_PREFIXES` (RPT-03), `contract.envelope`/exit codes, `cli.py` `_cmd_*` dispatch. **stdlib + PyYAML only (PyYAML already a dependency); NO new deps.**

### Agent's Discretion
- All implementation choices are at the agent's discretion (discuss skipped). Likely shape: a new generator module (`crawler/checklist.py`) + a `checklist` CLI verb that reads the profile, derives applicability into `basis[]`, retrieves+cites Layer-1 document requirements into gated `claims[]`, assembles the answer object, runs the gate, and renders to `personal/output/`. A synthetic `personal.example/profile.yaml` drives the test/demo end-to-end with zero real data.

### Deferred Ideas (OUT OF SCOPE)
- **Layer-2 rule matching** (recency / amounts / format / translation verification per document) — VAL-01. Phase 26 is **Layer-1 completeness only** ("which documents you need"), not "is each document valid."

## Project Constraints (from copilot-instructions.md)

> `.github/copilot-instructions.md` is the project directive file (`config.json.claude_md_path = ./copilot-instructions.md`; the repo file is `.github/copilot-instructions.md`). Actionable directives the planner MUST honor:

- **No PII may ever enter the public repo** — personal data and documents stay in a local, git-ignored area, structurally separated from the shareable harness. (This is the phase's whole point.)
- **All requirement claims must be backed by a citation** to the curated authoritative corpus (IRCC / IRPA / IRPR / PDIs) — **no ungrounded assertions**.
- **Source authority:** corpus limited to authoritative sources; no third-party/blog content.
- **CLI-agnostic harness:** tools invoked as ordinary CLI commands; no proprietary CLI dependencies in the trust path.
- ⚠️ The "Technology Stack" section of copilot-instructions.md is an **aspirational v0 research doc** (httpx, trafilatura, typer, pydantic, platformdirs, uv…). The **shipped** codebase uses **stdlib + argparse + PyYAML only** (+ `crawl4ai` behind the optional `crawl` extra). Phase 26's locked constraint is **stdlib + PyYAML, NO new deps** — do **not** introduce typer/pydantic/platformdirs. Follow the shipped conventions, not the STACK.md wishlist.

## Standard Stack

### Core (all already present — NO installs)
| Library / Module | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python (`.venv/bin/python`) | 3.10.12 | Runtime | Project venv. **Bare `python` is BROKEN** (pyenv-win CRLF shim → `/bin/sh^M: bad interpreter`). All commands MUST use `.venv/bin/python` or `poetry run`. [VERIFIED: ran `.venv/bin/python --version`] |
| PyYAML (`yaml`) | 6.0.3 | Parse `profile.yaml` via `yaml.safe_load` | Already a declared dependency (`pyproject.toml`); the existing crawl-profile loader (`crawler/profile.py`) parses YAML with `yaml.safe_load` ONLY (never `yaml.load` — threat T-13-01). [VERIFIED: `import yaml; yaml.__version__ == '6.0.3'`] |
| `crawler.grounding` | Phase 25 | `check_answer`, `render_answer`, `quote_is_grounded`, `InvalidAnswer` | The gate + renderer the producer emits into. [VERIFIED: read source] |
| `crawler.searchindex` | Phase 24 | `search(db,q,limit,family)`, `resolve(db,chunk_id)`, `EmptyQuery` | Retrieval + citation resolution; `resolve` returns `{chunk_id,relpath,source_url,title,section,crawl_date,text}` (text verbatim). [VERIFIED: ran search + `--cite`] |
| `scripts/check_publish_safe.py` | RPT-03 | `scan_text(path,text)`, `scan_path_name`, `CORPORA_PREFIXES`, `is_excluded` | Render-then-scan share-safety gate; `CORPORA_PREFIXES` already includes `personal/`. [VERIFIED: read source] |
| `crawler.contract` | AGENT-01 | `envelope(command,result,error)`, `emit`, `EXIT_*`, `INVALID_INPUT`/`INTERNAL_ERROR` | Frozen 5-key JSON envelope + exit codes. Adding a new `checklist` command string is additive. [VERIFIED: read source] |
| `argparse`, `json`, `os`, `pathlib`, `re` | stdlib | CLI verb, JSON I/O, `$PR_PERSONAL_DIR` env read, paths, slugging | Mirrors every existing `_cmd_*` handler. |

### Supporting (reuse, do not rebuild)
| Symbol | Purpose | When to Use |
|--------|---------|-------------|
| `cli._personal_root()` | `<repo>/personal` resolved | Anchor the output-containment check; tests monkeypatch it to a tempdir. |
| `cli._cmd_ground` render→scan→write block (cli.py:525–581) | The exact "verdict==pass → render → `scan_text` → write under `personal/`" path | Either call it via the answer-on-stdin pipe, OR factor the block into a shared helper and call it from the new `checklist` verb (cli.py-only edit; allowed). |
| `crawler/profile.py::load_profile` pattern (lines 142–181) | Reference for safe YAML loading + `ProfileError` fail-fast | Copy the `yaml.safe_load` + clear-error pattern; do NOT reuse the `SiteProfile` model (that's the unrelated crawl-site profile). |
| eval fixture `crawler/eval/questions.jsonl` | Canonical answer-object examples that resolve against the live index | Shape reference for each `claims[]` entry; the police-cert + medical lines show real `(citation, verbatim quote)` pairs. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New `checklist` CLI verb calling the gate in-process | `checklist --emit-answer` prints answer JSON to stdout, user pipes into `ground` | Pipe approach is more CLI-agnostic/composable (good for Phase 27 ethos) but two-step; in-process reuse is one command + simpler UX. Recommend **in-process** primary, support `--emit-answer` stdout for composability. |
| Derive the verbatim quote from the **live** resolved chunk at runtime | Hard-code `(chunk_id, quote)` per doc type (like `questions.jsonl`) | Hard-coded pairs are deterministic but go stale on re-crawl (`chunk_sha` drift → `resolve`→`None`→fail-closed). Runtime extraction survives re-chunking as long as the query still hits. Recommend **runtime extraction**; the eval harness catches any drift either way. |
| Cite **generic** rule pages (`guidance/police-certificates.md`) | Cite country-specific pages (`police-certificates/<country>.md`) | Country-specific relpath in the rendered output **leaks residence history** (PII). Recommend **generic** citations; per-country specifics go in `basis[]`/local only. |

**Installation:** None. `corpus-crawler` is already installed in `.venv`; PyYAML 6.0.3 already present. Verify before planning:
```bash
.venv/bin/python -c "import yaml; print(yaml.__version__)"   # → 6.0.3
.venv/bin/python -m crawler.cli --json search "police certificate permanent residence" --limit 1
```

## Package Legitimacy Audit

**Not applicable — this phase installs NO external packages.** The locked constraint is stdlib + PyYAML only, and PyYAML is an already-declared, already-installed dependency (`pyyaml>=6.0,<7.0`, resolved to 6.0.3 in `poetry.lock`). No registry lookups, no new imports.

- **Packages removed due to [SLOP] verdict:** none
- **Packages flagged as suspicious [SUS]:** none

## Profile Schema (design proposal — the `personal.example/profile.yaml` this phase CREATES)

> The schema is invented by this phase (no resolution exists today). It is **local config the user fills in**, not requirement text, so it carries no citation. Field choices are grounded in the corpus document list (`guidance/documents.md`, VERIFIED read) but the schema shape itself is a design recommendation. Keep it **minimal but realistic** for a post-ITA Express Entry applicant. The tracked `personal.example/profile.yaml` uses **sentinel fake PII** (see self-test).

Recommended minimal schema (fields → drive applicability):

```yaml
# personal.example/profile.yaml — SYNTHETIC example (no real data). Tracked.
applicant:
  citizenship: "Wakanda"              # SENTINEL country (fake) — passport applicability
  family_members_18_plus: 1           # count of accompanying family ≥18 → family police certs
program:
  stream: "CEC"                       # CEC | FSW | FST | PNP — drives proof-of-funds applicability
  has_job_offer: false                # written job offer letter applicability
education:
  claiming_foreign_education_points: true   # → ECA applicability
residence_since_18:                   # countries lived in ≥6 months in a row, last 10 yrs, since 18
  - country: "Wakanda"                # SENTINEL (fake)
    months: 240
    current: true
  - country: "Latveria"               # SENTINEL (fake)
    months: 14
    current: false
```

**Field → applicability semantics (pure logic, output → `basis[]`):**

| Profile field | Layer-1 item it gates | Rule (PII-free, from corpus) | Where the value goes |
|---------------|----------------------|------------------------------|----------------------|
| (always) | Passport / travel document | Express Entry profile needs a passport/travel document | `claims[]` (generic), no PII |
| (always) | Language test results | Express Entry requires an approved language test | `claims[]` (generic) |
| (always) | Immigration medical exam (IME) | PR applicants must undergo an IME | `claims[]` (generic) |
| (always) | Biometrics (fingerprints + photo) | Biometrics required for PR applications | `claims[]` (generic) |
| `education.claiming_foreign_education_points` or `stream==FSW` | ECA / proof of Canadian education | ECA required to claim foreign-education points (FSW) | include claim iff true; `basis[]` notes "because claiming foreign-education points" |
| `program.stream` | Proof of funds | FSW/FST must meet settlement-funds requirement; **CEC and arranged-employment-authorized candidates are exempt** | include claim iff stream ∈ {FSW, FST} and not exempt; `basis[]` records exemption reason |
| `residence_since_18[]` + `family_members_18_plus` | Police certificate(s) | One per country stayed ≥6 months in a row in the last 10 years, since age 18, for applicant + family ≥18 | include the (generic) police-cert claim iff any qualifying country; the **specific country list lives in `basis[]` only** |
| `program.has_job_offer` | Written job-offer letter | If you have a written job offer | include claim iff true |

**PII boundary in the schema:** countries, names, dates, counts are PII. They drive **which** claims appear and populate `basis[]`. They must **never** appear in `claims[].text`, the verbatim `quote`, the corpus DB, or any tracked file (other than the synthetic sentinel values in `personal.example/`).

## Doc-type → corpus retrieval map (VERIFIED chunks)

> Use **short, targeted** queries (2–4 content tokens). `_to_match` joins every token with implicit **AND** (`"police" "certificate" "since" "age" "18"`), so long queries over-restrict and return **zero hits**. [VERIFIED: `_to_match('police certificate since age 18')`]. Extract the `quote` as a verbatim span sliced from the live resolved chunk's `text`.

| Layer-1 item | Suggested query (short) | Verified target chunk | Verbatim span available (the grounded fact) |
|--------------|-------------------------|-----------------------|---------------------------------------------|
| Police certificate (generic rule) | `police certificate 10 years country` | `guidance/police-certificates.md#002` | "every country you (or a family member) stayed in during the last 10 years for **6 months in a row or longer**" [VERIFIED: resolved] |
| Document overview | (read directly) | `guidance/documents.md` | Lists passport, language test results, ECA, job offer, proof of funds, police certificates [VERIFIED: read] |
| Proof of funds / CEC exemption | `settlement funds requirement unless` | `pr-pdi/express-entry-assessing-electronic-application-on-section-a11-2.md#036` | "Candidates applying under the FSWC or the FSTC are required to meet the settlement funds requirement, unless they are c…" [VERIFIED: resolved] |
| ECA (foreign education) | `foreign educational credential assessment` | `eca/educational-credential-assessment.md#014` | assessment of authenticity of completed foreign educational credential [VERIFIED: top hit] |
| Language test | `official language test results` | `guidance/language-test.md#011` (points page) — **tune query**; consider `language/language-requirements.md` for the requirement statement | language test results for each ability [VERIFIED: hit; relevance tuning needed] |
| Immigration medical exam | `immigration medical examination permanent residence` | `medical/immigration-medical-assessment.md#001` (also fixture `medical/who-must-submit-immigration-medical-examination.md#000`) | "immigration medical examination is required if the applicant applies for permanent residence" [VERIFIED: hit] |
| Biometrics | `fingerprints photo biometrics permanent residence` | `guidance/after-apply.md#000` | give fingerprints and photo (biometrics) for permanent residence [VERIFIED: hit] |

**Per-item algorithm (each applicable item):**
1. `res = searchindex.search(db, query, limit=3)` → take best hit's `chunk_id` (handle `EmptyQuery`, zero hits → abstain or fail loudly, see pitfalls).
2. `chunk = searchindex.resolve(db, chunk_id)` → if `None` (miss/drift) fail-closed (don't emit an ungrounded claim).
3. `quote = <a verbatim span of chunk["text"]>` (e.g. a sentence containing the item's anchor phrase, or `chunk["text"][:N]`). Must be a real substring — `grounding.quote_is_grounded` normalizes whitespace+case but is otherwise exact.
4. Build `claim = {"id": doc_type, "text": <PII-free generic label>, "citations": [chunk_id], "quote": quote}`.
5. Add the item's PII applicability sentence to `basis[]`.

## Architecture Patterns

### System Architecture Diagram

```
 $PR_PERSONAL_DIR/profile.yaml  (env var, default ./personal/)   [PII — git-ignored]
            │  yaml.safe_load (NEVER yaml.load)
            ▼
 ┌─────────────────────────────────────────────┐
 │ checklist.load_profile(dir) -> dict          │
 └───────────────┬─────────────────────────────┘
                 │  pure applicability logic (PII in)
                 ▼
 ┌─────────────────────────────────────────────┐        basis[] (PII applicability)
 │ checklist.applicable_items(profile)          │───────────────────────┐
 │   -> [(doc_type, query, basis_text), ...]    │                        │
 └───────────────┬─────────────────────────────┘                        │
                 │  per item (generic, PII-free)                         │
                 ▼                                                       │
 ┌──────────────────────────┐   corpus/index.db (git-ignored, local)    │
 │ searchindex.search →      │◄──────────────────────────────────────┐  │
 │ searchindex.resolve       │  returns verbatim chunk text + cite     │  │
 └───────────────┬───────────┘                                        │  │
                 │ claim{id,text(PII-free label),citations[],         │  │
                 │       quote(verbatim span)}                        │  │
                 ▼                                                    │  │
 ┌─────────────────────────────────────────────┐ ◄──────────────────┘  │
 │ assemble answer{question, claims[], basis[]◄─────────────────────────┘
 │   abstentions[], prose}                      │
 └───────────────┬─────────────────────────────┘
                 │  grounding.check_answer(answer, db)   [Phase-25 GATE]
                 ▼
        verdict == "fail"? ──yes──► emit ok:true result.verdict:"fail", exit 1, WRITE NOTHING
                 │ no (pass)
                 ▼
 grounding.render_answer(answer, db)  ── renders claims+quote+citation ONLY, never basis[]
                 │
                 ▼
 check_publish_safe.scan_text("answer.md", rendered)  [RPT-03]
                 │ violations? ──yes──► ok:false internal_error, exit 4, WRITE NOTHING
                 │ no
                 ▼
 anchored containment: out_dir.resolve() under <repo>/personal  (CR-03)
                 ▼
 write rendered .md under  personal/output/   [PII-free bytes, git-ignored dir]
                 ▼
 contract.envelope("checklist", result=...) on stdout (--json); human → stderr
```

### Recommended Project Structure
```
crawler/
├── checklist.py        # NEW: load_profile + applicable_items + build_answer (pure-ish compute)
├── cli.py              # EDIT: add `checklist` subparser + _cmd_checklist (thin dispatch, reuse ground's render→scan→write)
└── tests/
    └── test_checklist.py   # NEW: stdlib unittest; synthetic-corpus unit tests + @skipUnless real-corpus integration + PII self-scan
personal.example/
└── profile.yaml        # NEW (tracked): synthetic sentinel profile that drives the demo/test
personal/               # git-ignored: real profile.yaml + output/ (rendered checklists)
└── output/             # rendered, PII-free checklist bytes
```

### Pattern 1: PII-tier split (the defining pattern)
**What:** Requirement text + citation = generic, gated, in `claims[]`. Applicability = PII, in `basis[]`, never gated, never rendered.
**When to use:** Every applicable item.
**Example (verified to pass `ground` this session):**
```python
# Source: end-to-end run this session against corpus/index.db → verdict "pass"
answer = {
  "question": "Personalized Layer-1 document checklist",
  "claims": [{
    "id": "police-certificates",
    "text": "You need a police certificate for every country you (or a family member 18+) "
            "stayed in during the last 10 years for 6 months in a row or longer.",  # PII-FREE
    "citations": ["guidance/police-certificates.md#002"],
    "quote": "every country you (or a family member) stayed in during the last 10 years "
             "for **6 months in a row or longer**",  # verbatim span of the resolved chunk
  }],
  "basis": ["Applies because profile lists residence in 2 countries since age 18 "
            "(countries kept local; not shown in claim text)."],  # PII lives ONLY here
  "abstentions": [], "prose": "",
}
# grounding.check_answer(answer, db) -> {"verdict":"pass", ...}
```

### Pattern 2: Reuse the `ground` render→scan→write path verbatim
**What:** Don't re-implement render/scan/write. Either pipe the answer JSON into the existing `ground` verb, or factor cli.py:525–581 into a shared helper and call it from `_cmd_checklist`.
**When to use:** After `check_answer` returns `verdict:"pass"`.
**Why:** The anchored-containment check (CR-03), the neutral-label scan (WR-01: `scan_text("answer.md", ...)` to avoid self-exclusion), and the fail-closed refusal codes are all already correct and tested — re-deriving them risks regressing the PII guard.

### Pattern 3: Personalization = claim SELECTION, not text mutation
**What:** A CEC applicant's checklist **omits** the proof-of-funds claim; an applicant claiming foreign-education points **includes** the ECA claim. The requirement *text* never changes per user — only the *set* of claims and the `basis[]` reasons do.
**Why:** Keeps every emitted claim a verbatim-grounded generic statement; the personalization carries no PII into the gated artifact.

### Anti-Patterns to Avoid
- **PII in `claims[].text` or `quote`:** never put a country/name/date in a gated claim or its quote — it would land in the rendered, tracked-adjacent artifact. PII goes in `basis[]` only.
- **Citing country-specific pages:** `police-certificates/south-africa.md` reveals residence → cite the generic rule page instead.
- **Long AND-queries:** `searchindex._to_match` ANDs every token; 5+ tokens → zero hits → no citation → broken item.
- **Hand-written requirement text presented as fact:** every requirement line MUST carry a resolving citation + verbatim quote; never a bare string literal.
- **Re-implementing resolve/scan/containment:** reuse the shipped functions.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parse `profile.yaml` | A custom YAML/key parser, or `yaml.load` | `yaml.safe_load` | `safe_load` blocks arbitrary-object construction (threat T-13-01); matches `crawler/profile.py`. |
| Resolve a citation id to chunk text | A new SQLite query | `searchindex.resolve(db, chunk_id)` | Handles read-only open, `UNIQUE(chunk_id)`, and `chunk_sha` drift→`None` (fail-closed). |
| Check a claim is grounded | A custom substring check | `grounding.check_answer` / `quote_is_grounded` | Exact `_norm` (whitespace+lowercase only); rejects empty/whitespace/non-string quotes (CR-01/CR-02). |
| Render the checklist | A bespoke markdown builder | `grounding.render_answer` | Renders only claims+quote+citation (never `basis[]`) → PII-free by construction; adds the honesty footer. |
| Stop PII reaching disk | A custom PII regex | `check_publish_safe.scan_text` over rendered bytes + the PII-tier architecture | RPT-03 secondary guard; the primary guard is "PII only in `basis[]`, never rendered." |
| Confine output to a safe dir | An ad-hoc `if "personal" in path` | `cli._personal_root()` + anchored `resolve()` containment (CR-03) | Rejects `/tmp/personal`, `~/personal`, traversal; the naïve check was a real prior bug. |
| Machine output + exit codes | New JSON shape | `contract.envelope("checklist", ...)` / `EXIT_*` | Frozen 5-key contract; only the new command string is additive. |

**Key insight:** The grounding gate, resolver, renderer, scanner, and containment check already exist and were exercised this session. Phase 26 is **~one new pure module + one thin CLI verb + one synthetic fixture** — the trust path is entirely reuse. The only genuinely new judgement is the **profile→applicability mapping** (pure logic) and the **query→verbatim-quote extraction** per item.

## Runtime State Inventory

> This phase CREATES new tracked state (`personal.example/profile.yaml`) and new git-ignored runtime state (`personal/profile.yaml`, `personal/output/*.md`). It is not a rename/refactor, but the PII boundary makes a state inventory worthwhile.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `corpus/index.db` (14.3 MB, ~742 docs) is the grounding source. **Git-ignored** (`corpus/`, `*.db`) and locally built — NOT tracked (`git ls-files corpus/` → 0). | Integration tests must `@skipUnless(corpus/index.db is_file())`; unit tests build a synthetic tiny index in a tempdir (mirror `test_grounding.setUp`). |
| Live service config | None — no external service; all local. | None. |
| OS-registered state | None. | None. |
| Secrets / env vars | NEW env var `$PR_PERSONAL_DIR` (default `./personal/`) read by the generator. Not a secret. | Resolve via `os.environ.get("PR_PERSONAL_DIR", "personal")`; document default. |
| Build artifacts | None new. `personal/output/` already exists (a stale `smoke-test-grounded-question.md` from Phase 25 testing is present, git-ignored). | None; `personal/output/` is git-ignored runtime output. |
| Tracked-tree additions | NEW tracked file `personal.example/profile.yaml` (the ONLY tracked profile). `personal.example/` does not exist yet. | Create it with sentinel PII; verify `git ls-files personal/` stays empty and `CORPORA_PREFIXES` fails closed if `personal/` is ever staged. |

**Verified:** `git ls-files personal/ personal.example/` → empty (no tracked profile artifacts today); `git ls-files corpus/` → 0 (corpus + index are local-only).

## Common Pitfalls

### Pitfall 1: PII in the gated claim text or quote
**What goes wrong:** A country/name/date placed in `claims[].text` or `quote` is rendered into `personal/output/` and would also appear if an answer line were ever committed (e.g. as a fixture).
**Why it happens:** Conflating "the requirement (generic)" with "why it applies to me (PII)."
**How to avoid:** `claims[].text` = generic label; PII only in `basis[]` (never gated, never rendered). Self-test asserts no sentinel token appears in `claims[].text` or rendered bytes.
**Warning signs:** A claim's `text` mentions a specific country/date; `render_answer` output contains a profile value.

### Pitfall 2: Country-specific citation leaks residence history
**What goes wrong:** Citing `police-certificates/<country>.md` puts the country in the rendered `relpath`, leaking where the user lived.
**Why it happens:** Country-specific "how to get a certificate" pages are tempting and useful.
**How to avoid:** Cite the **generic** rule page (`guidance/police-certificates.md`); keep per-country specifics in `basis[]`/local. (Phase 27 document agents can answer per-country questions interactively.)
**Warning signs:** A citation relpath under a country-named corpus family appears in the rendered checklist.

### Pitfall 3: Over-long search query → zero hits → ungrounded item
**What goes wrong:** `searchindex.search` ANDs all tokens; a 5+ token query returns 0 hits, so the item has no citation and either fails the gate or is silently dropped.
**Why it happens:** Writing a query like a sentence. [VERIFIED: `_to_match('police certificate since age 18')` → `"police" "certificate" "since" "age" "18"` (implicit AND).]
**How to avoid:** 2–4 high-signal tokens; verify each query returns ≥1 hit at plan time using the verified map above. Handle `EmptyQuery` and zero-hit explicitly (emit an `abstention`, or fail loudly — never a bare uncited claim).
**Warning signs:** `result.count == 0` for an applicable item.

### Pitfall 4: Hand-rolled requirement text instead of a cited quote
**What goes wrong:** The generator embeds IRCC rule text as a string literal and presents it as fact with no resolving citation.
**Why it happens:** It's easier to hard-code than to retrieve.
**How to avoid:** Every claim carries `citations[]` + a verbatim `quote` sliced from the live resolved chunk; the gate refuses anything else. Derive the quote at runtime so it can't drift from the corpus.
**Warning signs:** A claim with empty `citations` or a `quote` not present in any resolved chunk → `uncited`/`unresolvable`/`quote_not_in_chunk`.

### Pitfall 5: Accidentally tracking `personal/`
**What goes wrong:** `git add personal/profile.yaml` (or `personal/output/...`) ships PII.
**Why it happens:** Glob `git add`, or forgetting the boundary.
**How to avoid:** `.gitignore` already ignores `personal/` + un-ignores `!personal.example/`. `check_publish_safe.scan_path_name` returns a `TRACKED_CORPORA` violation (exit 1) for any tracked `personal/` path — keep that guard green. The ONLY tracked profile is `personal.example/profile.yaml`.
**Warning signs:** `git ls-files personal/` non-empty; `scripts/check_publish_safe.py` reports `TRACKED_CORPORA`.

### Pitfall 6: Quote drift on corpus re-crawl
**What goes wrong:** A hard-coded `(chunk_id, quote)` no longer resolves after re-chunking (`chunk_sha` mismatch → `resolve`→`None`), failing the gate.
**Why it happens:** Corpus is regenerated locally; chunk ids/sha can change.
**How to avoid:** Retrieve + extract the quote at runtime; if you do curate fixed pairs, re-verify them via the eval harness. Fail-closed is correct here — better a refused checklist than a stale citation.
**Warning signs:** Eval/integration tests flip to `unresolvable`/`quote_not_in_chunk` after a re-index.

### Pitfall 7: Writing output outside `personal/`
**What goes wrong:** A relative/absolute `--out-dir` writes verbatim corpus text outside `.gitignore` protection.
**Why it happens:** Trusting the path string.
**How to avoid:** Reuse the anchored containment check (CR-03): `out_dir.resolve()` must equal or be nested under `cli._personal_root()`; else `invalid_input`/exit 2.
**Warning signs:** Rendered `.md` appearing outside `personal/`.

### Pitfall 8: `bare python` breaks the toolchain
**What goes wrong:** `python -m crawler.cli ...` fails with `/bin/sh^M: bad interpreter` (pyenv-win CRLF shim).
**How to avoid:** Always `.venv/bin/python` or `poetry run`. Do NOT use `gsd-tools state advance-plan`.

## Code Examples

### Resolve `$PR_PERSONAL_DIR` (new — no resolution exists today)
```python
# Source: convention to add (no prior resolver in the codebase; verified via grep)
import os
from pathlib import Path

def personal_dir() -> Path:
    """Profile/output root. Env override, default ./personal/ (git-ignored)."""
    return Path(os.environ.get("PR_PERSONAL_DIR", "personal"))

def load_profile(root: Path) -> dict:
    text = (root / "profile.yaml").read_text(encoding="utf-8")
    import yaml
    data = yaml.safe_load(text)          # safe_load ONLY (T-13-01); never yaml.load
    if not isinstance(data, dict):
        raise ValueError("profile.yaml must be a mapping")
    return data
```

### Build one grounded, PII-free claim from the live corpus
```python
# Source: searchindex.search/resolve + grounding contract (read this session)
from crawler import searchindex, grounding

def grounded_claim(db, doc_type, query, generic_text):
    res = searchindex.search(db, query, limit=3)        # short query (implicit AND!)
    if res["count"] == 0:
        return None                                      # caller abstains / fails loudly
    chunk_id = res["hits"][0]["chunk_id"]
    chunk = searchindex.resolve(db, chunk_id)            # None on miss/drift → fail-closed
    if chunk is None:
        return None
    quote = chunk["text"][:120]                          # a VERBATIM span of the live chunk
    return {"id": doc_type, "text": generic_text,        # generic_text = PII-FREE label
            "citations": [chunk_id], "quote": quote}
```

### Reuse the gate + render→scan→write (mirror `_cmd_ground`)
```python
# Source: cli.py:509-581 (read this session). Either pipe answer JSON into `ground`,
# or factor the render→scan→write block into a helper and call it here.
result = grounding.check_answer(answer, db)
if result["verdict"] != "pass":
    # ok:true, result.verdict:"fail", exit 1, write NOTHING
    return contract.envelope("checklist", result=result), 1
rendered = grounding.render_answer(answer, db)           # never renders basis[]
violations = cps.scan_text("answer.md", rendered)        # neutral label (WR-01)
if violations:
    return contract.envelope("checklist", error=(contract.INTERNAL_ERROR,
            "refusing to write checklist: publish-safety violation(s)")), 4
# anchored containment: out_dir.resolve() under cli._personal_root() else invalid_input/exit 2
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "checklist.md").write_text(rendered, encoding="utf-8")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ungrounded/hand-written checklists | Grounding-by-construction: every line cited + verbatim-quote-checked, fail-closed | v3.0 (Phase 25) | The checklist producer MUST emit the gate's answer shape; there is no "trust me" path. |
| PII mingled with logic | Structural PII separation: `personal/` git-ignored, PII only in `basis[]`, generic text in `claims[]` | v1.0 invariant, enforced by RPT-03 + `.gitignore` | The checklist's whole design is the separation; rendered bytes are PII-free by construction. |

**Deprecated/outdated:**
- The STACK.md wishlist (typer/pydantic/platformdirs/httpx/trafilatura) is **not** the shipped stack. Phase 26 uses stdlib + PyYAML only.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The minimal `profile.yaml` schema fields (citizenship, residence_since_18, family_members_18_plus, stream, claiming_foreign_education_points, has_job_offer) are sufficient for a post-ITA Express Entry Layer-1 checklist. | Profile Schema | A missing field would drop an applicable document. Schema is the agent's discretion; easy to extend. The corpus document list (`guidance/documents.md`, VERIFIED) is the authority for which items can exist. |
| A2 | Citing **generic** rule pages (not country-specific) is the right tradeoff for keeping rendered output PII-free. | Pattern/Pitfall 2 | If users need per-country specifics in the *checklist itself*, generic citations under-serve them. Mitigation: per-country detail in `basis[]`/local, or via Phase 27 agents. Recommend confirming with the user during planning. |
| A3 | Deriving the verbatim `quote` at runtime from the top search hit yields a *representative* requirement span. | Doc-type map / Code Examples | A poor query could quote an off-topic span (gate still passes — honesty boundary only guarantees verbatim presence, not semantic support). Mitigation: curate per-item queries + verify hits at plan time using the VERIFIED map. |
| A4 | The `language` requirement is best cited from a requirement page rather than the CRS points page (`guidance/language-test.md#011`). | Doc-type map | A points-page quote may read as a scoring rule, not a "you must submit test results" requirement. Mitigation: tune the query (e.g. `language/language-requirements.md`) during planning. |

## Open Questions (RESOLVED)

> All resolved by the orchestrator and implemented in the plans:
> **Q1 (show basis[]?)** — RESOLVED: gated render stays PII-free (claims[] only); an applicability view is local-only/optional.
> **Q2 (in-process vs --emit-answer)** — RESOLVED: in-process `checklist` verb is primary; `--emit-answer` optional (Plan 03).
> **Q3 (zero-hit UX)** — RESOLVED: emit an explicit `abstention`, never an empty/ungrounded checklist (Plan 02 `build_answer`).


1. **Should `basis[]` applicability be shown to the user at all (and if so, where)?**
   - What we know: `render_answer` renders only `claims[]`+quote+citation, never `basis[]`. So the gated/scanned artifact is PII-free but does NOT show "you specifically need certs for X and Y."
   - What's unclear: whether the user wants a separate, local-only personalized view that DOES list their specific countries/reasons.
   - Recommendation: keep the gated rendered checklist PII-free (cite generic). If a personalized "why each applies" view is wanted, write it as a SEPARATE local-only file under `personal/output/` (git-ignored), explicitly NOT scanned-as-PII-free, and never a fixture. Confirm during planning.

2. **In-process `checklist` verb vs `--emit-answer` + pipe into `ground`?**
   - What we know: both reuse the gate; pipe is more CLI-agnostic (Phase 27 ethos), in-process is simpler UX.
   - Recommendation: implement in-process primary (`checklist` runs gate+render+scan+write), and also support `checklist --emit-answer` to print the answer JSON to stdout for composability/testing.

3. **Zero-hit / no-applicable-item behavior:** if a query returns 0 hits or no items apply, emit an explicit `abstention` (mirroring the eval's `must_abstain` lines) rather than an empty/uncited checklist. Confirm the desired UX.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv/bin/python` | Everything (bare `python` broken) | ✓ | 3.10.12 | None — MUST use `.venv/bin/python` / `poetry run` |
| PyYAML (`yaml`) | profile parsing | ✓ | 6.0.3 | None needed (already a dep) |
| `corpus-crawler` (installed pkg: grounding/searchindex/contract) | gate + retrieval | ✓ | editable install in `.venv` | None |
| `corpus/index.db` (FTS5 index, ~742 docs) | grounding any real claim | ✓ (present, **git-ignored/local-only**) | 14.3 MB, built 2026-06-21 | Unit tests build a synthetic tiny index (tempdir); integration test `@skipUnless` its presence |
| `scripts/check_publish_safe.py` | RPT-03 scan | ✓ | in repo | None |
| `git` (for `scan_path_name`/tracked-tree scan) | publish-safety self-gate | ✓ | available | None |
| Network / new packages | — | n/a | — | Not used — offline, stdlib + PyYAML only |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `corpus/index.db` is local-only — real-corpus tests must skip-guard on its presence; synthetic-corpus unit tests cover the always-run path.

## Validation Architecture

> `workflow.nyquist_validation: true` → section included. House rule (AGENTS.md / `test_grounding.py`): **stdlib `unittest` ONLY — no pytest fixtures, no network, no browser.** Drive every test from a SYNTHETIC tiny corpus built into a `tempfile.TemporaryDirectory` via `searchindex.build_index`; never walk the real `corpus/`.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | stdlib `unittest` (run via `pytest` or `python -m unittest`) |
| Config file | none (no pytest.ini/pyproject pytest config — discovery only) |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_checklist.py -q` |
| Full suite command | `.venv/bin/python -m pytest crawler/tests -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CHK-01 | Generator against `personal.example/profile.yaml` produces an answer whose every claim passes `check_answer` (synthetic corpus) | unit | `pytest crawler/tests/test_checklist.py -k grounds -x` | ❌ Wave 0 |
| CHK-01 | Applicable items reflect profile (CEC omits proof-of-funds; foreign-education includes ECA) | unit | `pytest crawler/tests/test_checklist.py -k applicability -x` | ❌ Wave 0 |
| CHK-01 | End-to-end against the LIVE 742-doc index (grounded) | integration (`@skipUnless corpus/index.db`) | `pytest crawler/tests/test_checklist.py -k real_corpus -x` | ❌ Wave 0 |
| CHK-02 | No sentinel PII token from `personal.example/profile.yaml` appears in `claims[].text` or rendered bytes | unit (NOT skip-guarded) | `pytest crawler/tests/test_checklist.py -k pii -x` | ❌ Wave 0 |
| CHK-02 | `check_publish_safe.scan_text` over rendered checklist bytes == [] | unit (NOT skip-guarded) | `pytest crawler/tests/test_checklist.py -k publish_safe -x` | ❌ Wave 0 |
| CHK-02 | `git ls-files personal/` is empty; `personal.example/profile.yaml` IS tracked; `scan_path_name("personal/x")` fails closed | unit | `pytest crawler/tests/test_checklist.py -k tracked -x` | ❌ Wave 0 |
| CHK-02 | Output written outside `personal/` is rejected (anchored containment, CR-03) | unit | `pytest crawler/tests/test_checklist.py -k containment -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest crawler/tests/test_checklist.py -q`
- **Per wave merge:** `.venv/bin/python -m pytest crawler/tests -q`
- **Phase gate:** full test suite green before `/gsd-verify-work`, AND the Phase-26-relevant publish-safety invariants hold: (a) `scan_path_name` returns no `TRACKED_CORPORA` for any `personal/` path (i.e. `git ls-files personal/` stays empty), and (b) `scan_text` over the rendered checklist bytes returns `[]`.
  - ⚠️ **Pre-existing caveat (verified this session):** a whole-tree `scripts/check_publish_safe.py` run currently reports ~22 `ABS_PATH` violations — all in files **outside this phase** (Phase-25 planning docs under `.planning/phases/25-*`, a quick-task doc, and `crawler/tests/test_grounding.py:878` which literally asserts on `/home/`,`/Users/`,`pr-ai-venv` markers). The scanner self-excludes `scripts/tests/` but **not** `crawler/tests/`. Do NOT make "whole-tree scan exit 0" a Phase-26 gate — it is unrelated tech debt. Phase 26 must (i) add **zero** new violations and (ii) keep the `personal/`-corpora + rendered-bytes guards green. <!-- # publish-safe: allow -->

### Wave 0 Gaps
- [ ] `personal.example/profile.yaml` — synthetic profile with **sentinel** PII tokens (fake countries like `Wakanda`/`Latveria`, fake name, fake dates) that the PII self-scan asserts never leak. (Required; drives the whole test.)
- [ ] `crawler/tests/test_checklist.py` — unit tests (synthetic corpus, reuse `test_searchindex._make_index_corpus` / `test_grounding` base) + `@skipUnless(corpus/index.db)` integration + NOT-skip-guarded PII/publish-safe self-scans (mirror `TestFixturePublishSafety`).
- [ ] No framework install needed — `unittest` is stdlib; corpus builder reused from `searchindex.build_index`.

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1` → section included.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface (local CLI). |
| V3 Session Management | no | None. |
| V4 Access Control | no | Single local user. |
| V5 Input Validation / Deserialization | **yes** | `yaml.safe_load` ONLY for `profile.yaml` (never `yaml.load`); validate the parsed structure is a dict; validate enum-ish fields (stream). The untrusted profile is local but still untrusted input. |
| V6 Cryptography | no | No secrets/crypto in this phase. |
| V12 File / Path Handling | **yes** | Anchored output containment (CR-03): `out_dir.resolve()` must be under `<repo>/personal`; reject traversal/absolute escapes. `$PR_PERSONAL_DIR` is a path — resolve and treat as untrusted. |
| (project invariant) PII confidentiality | **yes** | PII only in `basis[]` (never gated/rendered); `.gitignore` + `CORPORA_PREFIXES` fail-closed; RPT-03 scan over rendered bytes. |

### Known Threat Patterns for {stdlib CLI + YAML + local PII}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| YAML deserialization of arbitrary objects | Tampering / Elevation | `yaml.safe_load` only (existing T-13-01 control in `crawler/profile.py`). |
| Path traversal via `$PR_PERSONAL_DIR` / `--out-dir` | Tampering | Anchored `resolve()` containment under `<repo>/personal` (CR-03, reused). |
| PII exfiltration into tracked tree / rendered output | Information Disclosure | Architectural: PII in `basis[]` only, never rendered; `.gitignore` ignore `personal/`; `scan_path_name` fails closed on tracked `personal/`; `scan_text` over rendered bytes; sentinel-token self-test. |
| Ungrounded / fabricated requirement | Spoofing (false authority) | Fail-closed grounding gate: every claim needs a resolving citation + verbatim quote, else the whole checklist is refused. |
| Stale citation after re-crawl | Tampering / Integrity | `resolve` recomputes `chunk_sha` → drift returns `None` → fail-closed; eval harness catches it. |

## Sources

### Primary (HIGH confidence — read/executed this session)
- `crawler/grounding.py` — `check_answer`, `render_answer`, `quote_is_grounded`, `check_claim`, `run_eval`, `InvalidAnswer`, `_norm` (verbatim read).
- `crawler/cli.py` — `_cmd_ground` (render→scan→write, CR-03 anchored containment, WR-01 neutral scan label), `_cmd_search`, `_personal_root`, `build_parser`, `main` (verbatim read).
- `crawler/searchindex.py` — `search`, `resolve`, `_to_match` (implicit-AND), `EmptyQuery`, chunk/citation schema (verbatim read + executed `search`/`--cite`).
- `crawler/contract.py` — envelope (5 keys, schema_version "1.0"), `EXIT_*`, error types (verbatim read).
- `scripts/check_publish_safe.py` — `scan_text`, `scan_path_name`, `CORPORA_PREFIXES` (incl. `personal/`), `is_excluded` (verbatim read).
- `.gitignore` — `personal/` ignored + `!personal.example/` un-ignored (verbatim read).
- `pyproject.toml` — `pyyaml>=6.0,<7.0`, no other runtime deps; `.venv/bin/python -c "import yaml"` → 6.0.3 (verified).
- `crawler/eval/questions.jsonl` — canonical answer-object examples resolving against the live index (read).
- `crawler/tests/test_grounding.py` — synthetic-corpus + `@skipUnless` real-corpus + NOT-skip-guarded PII self-scan test patterns (read).
- Live corpus queries executed: `guidance/police-certificates.md#002` (police rule), `pr-pdi/...a11-2.md#036` (CEC funds exemption), `eca/...#014`, `guidance/language-test.md#011`, `medical/immigration-medical-assessment.md#001`, `guidance/after-apply.md#000`, `guidance/documents.md` (document list) — all VERIFIED to resolve/hit. End-to-end `ground` run → `verdict:"pass"`.
- `.planning/`: REQUIREMENTS.md (CHK-01/02, VAL-01 deferred), STATE.md, ROADMAP.md (Phase 26 success criteria + Phase 27 5-document list), 26-CONTEXT.md, config.json (nyquist_validation/security_enforcement true).

### Secondary (MEDIUM confidence)
- `crawler/profile.py` — `load_profile`/`safe_load`/`ProfileError` pattern (the YAML-loading reference, distinct concept from the checklist profile).
- `.github/copilot-instructions.md` — project constraints (no-PII, grounding) + the aspirational STACK.md (flagged as NOT the shipped stack).

### Tertiary (LOW confidence)
- Express Entry document-applicability domain knowledge (which documents map to which profile fields) — grounded against `guidance/documents.md` where possible; profile schema shape is a design proposal (Assumptions A1–A4).

## Metadata

**Confidence breakdown:**
- Standard stack / reuse surface: HIGH — every reused symbol read in source and exercised this session; no new deps.
- Architecture (PII-tier split, render-then-scan, containment): HIGH — verified end-to-end (`ground` → pass → rendered → scanned) and against the shipped guards.
- Corpus citability of Layer-1 items: HIGH for police/funds/medical/biometrics/ECA (resolved/searched live); MEDIUM for language (query tuning needed).
- Profile schema: MEDIUM — design proposal at the agent's discretion, grounded in the corpus document list; fields/queries to confirm at plan time.
- Pitfalls: HIGH — derived from shipped code comments (CR-01/02/03, WR-01) and verified behaviors (implicit-AND, `chunk_sha` drift, anchored containment).

**Research date:** 2026-06-21
**Valid until:** 2026-07-21 (stable; the corpus/index is regenerated locally so chunk ids can drift on re-crawl — the eval harness is the canary).
