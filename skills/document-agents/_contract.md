# Document Agents — Shared Answer-Object Contract

A **portable, CLI-agnostic** contract. It is plain Markdown with no proprietary
front-matter and no dependency on any single agent CLI's tool API. Any agent —
Antigravity, OpenAI Codex, Claude, GitHub Copilot, Gemini, or a plain shell
script — can follow it, because every trust-path step is **an ordinary shell
command plus JSON parsing**. There is no proprietary tooling, MCP server, or
per-CLI plugin to install. This is the single source of truth that every
document agent in this pack (see [`README.md`](README.md) for the full list —
`police-certificate.md`, `medical.md`, `passport.md`, `job-offer.md`,
`marriage-certificate.md`, …) links back to so they stay thin and behave
identically across CLIs.

This contract ships **no new trust-path code**. Every hard guarantee —
resolution, grounding, quote normalization, render, PII containment — is already
shipped and frozen by the Phase 24/25/26 primitives (`crawler/searchindex.py`,
`crawler/grounding.py`, `crawler/checklist.py`). The agents are authors that
*drive* those primitives; they never re-implement them. See
[`../../crawler/AGENT_SKILL.md`](../../crawler/AGENT_SKILL.md) for the pipeline
skill and [`../../crawler/CONTRACT.md`](../../crawler/CONTRACT.md) for the
machine contract (envelope schema, every field, exit codes, the
stdout=JSON / stderr=human invariant).

## Critical environment

Bare `python` is **BROKEN** in this repo (a pyenv-win CRLF shim resolves to a
`/bin/sh` with a carriage-return interpreter). Every worked example below uses
the `corpus-crawler` console script for the verb and `.venv/bin/python` (or
`jq`) for JSON parsing — **never** bare `python` and never bare `pytest`. Run
conformance tests with `.venv/bin/python -m pytest`. Run everything from
`<repo-root>` so the `crawler` package imports.

## The `--json` invariant

Invoke `corpus-crawler` as an ordinary shell command. To get a machine-readable
result, add the global `--json` flag **before** the subcommand:

```
corpus-crawler --json <subcommand> [args...]
```

- **stdout** is exactly **one JSON object** — capture it and parse it.
- **stderr** is human/progress/log text — surface it as diagnostics; never
  parse it.

Every `--json` response is the same five-key envelope:

```json
{
  "schema_version": "1.0",
  "ok": true,
  "command": "ground",
  "result": { "...": "per-command payload" },
  "error": null
}
```

**Read `ok` first.** If `ok` is `true`, read `result`. If `ok` is `false`, read
`error.type` and `error.message`. The per-command `result` field names live in
[`../../crawler/CONTRACT.md`](../../crawler/CONTRACT.md).

## The structured answer object

Every agent emits exactly **one** answer object of this shape — the schema is
defined canonically in `crawler/grounding.py`:

```json
{
  "question":    "<the question this answer addresses>",
  "claims":      [{ "id": "<str>", "text": "<generic label>", "citations": ["<relpath#NNN>"], "quote": "<verbatim span>" }],
  "basis":       ["<free-form supporting material — may carry PII>"],
  "abstentions": [{ "text": "<plain-language non-answer>", "reason": "<machine reason, e.g. not_in_corpus>" }],
  "prose":       "<human-readable narration>"
}
```

The five keys are: **`question`**, **`claims`**, **`basis`**, **`abstentions`**,
**`prose`**.

**The grounding gate inspects `claims[]` ONLY.** `basis`, `abstentions`, and
`prose` are free-form filler and are **never** citation-checked. This is exactly
what makes personal data in `basis[]` safe (see the PII-tier split below): the
gate cannot leak it because it never renders or grounds it.

Each entry in `claims[]` carries four required keys: `id`, `text`,
`citations[]` (a list of chunk ids), and `quote` (a verbatim span). A missing
key, or a `quote` whose value is **not a string** (a JSON `null` / `true` /
number), is malformed input → `invalid_input` / **exit `2`** (the gate refuses
to `str()`-coerce a non-string `quote` into a near-match token).

## The grounding-by-construction loop (search → resolve → verbatim-quote → ground → abstain)

This is the producer loop every agent runs for each requirement element. It
mirrors `crawler/checklist.py:grounded_claim` in prose — drive the shipped
primitives, never re-implement them:

1. **Read the local profile slice** for applicability (which countries, dates,
   counts, employer apply). Anything personal it yields goes to `basis[]` ONLY
   — never into a claim.

2. **Search** the read-only keyword index with a **2–4 high-signal-token**
   query (the index ANDs every token, so a long natural-language query returns
   zero hits — bake the short query, not a chunk id):

   ```bash
   corpus-crawler --json search "<2-4 token query>" --db corpus/index.db --limit 5
   ```

   Read `result.hits` (BM25-ranked, best-first; may be empty). For agents whose
   relpaths can leak residence history (e.g. police certificates), constrain
   retrieval with `--family guidance` and **skip any per-country relpath**.

3. **Resolve** the chosen hit back to its exact stored chunk:

   ```bash
   corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db
   ```

   Read `result.found` and `result.chunk.text`. The `text` field is the
   **exact verbatim quotable span** — **never** the `snippet`, which is a
   highlighted display-only preview. An unknown or content-drifted id is
   fail-closed: `found:false`, `chunk:null` — treat it as a miss and abstain.

4. **Copy a verbatim substring** of `result.chunk.text` into the claim's
   `quote`. Copy it verbatim at runtime — never paraphrase, and never inline a
   pasted corpus span into this contract or an agent body.

5. **Assemble** the answer object (generic claims; personal data in `basis`)
   and **ground** it by piping it to the gate on stdin:

   ```bash
   corpus-crawler --json ground --db corpus/index.db <<'JSON'
   {"question":"<question>",
    "claims":[{"id":"<id>","text":"<generic PII-free label>",
               "citations":["<relpath#NNN>"],
               "quote":"<verbatim span copied from result.chunk.text>"}],
    "basis":["<personal applicability sentence>"],
    "abstentions":[],"prose":""}
   JSON
   ```

   The `quote` field above is a **placeholder token**, not a real corpus span —
   the agent fills in the real verbatim quote it copied in step 4.

## The pass rule and the three fail reasons

`corpus-crawler --json ground` returns `result.verdict`. A claim passes iff
**at least one** of its citations BOTH resolves AND the verbatim `quote` is a
whitespace/case-normalized substring of that resolving chunk's stored text.
Normalization is whitespace-collapse + lowercase ONLY (and nothing else); a
paraphrase fails closed. **Any** single failing claim makes the whole-answer
`verdict:"fail"`.

A failing claim contributes one of three fail-closed reasons:

| Reason | Meaning |
|---|---|
| `uncited` | `citations` is absent / not a list / empty. |
| `unresolvable` | Every cited id failed resolution (unknown id OR sha-drift). |
| `quote_not_in_chunk` | At least one citation resolved, but the verbatim quote is not a normalized substring of any resolving chunk's text. |

A malformed shape (missing required claim key, or a non-string `quote`) is **not**
a verdict-fail — it is `invalid_input` / **exit `2`** before grounding runs.

**Verdict-fail is NOT an execution error.** A `verdict:"fail"` is `ok:true`,
`error:null`, **exit `1`**, and renders / writes **nothing**. On a
`verdict:"pass"` the answer is rendered (each claim beside its verbatim quote),
share-safety-scanned, and only a clean scan is written — to the git-ignored
`personal/output/` boundary ONLY (`result.out`). Branch on `result.verdict`,
not on `ok`.

## The PII-tier split (claims generic, basis personal)

This is what makes rendered output PII-free **by construction**:

- **`claims[].text` / `quote` / `citations`** carry **GENERIC, PII-free** corpus
  content only — a requirement label and the verbatim span that grounds it.
- **`basis[]`** carries **all** personalization: countries of residence, dates,
  family/dependant counts, employer name, salary, applicant name. The gate never
  inspects `basis[]`, and the renderer never renders it.

Because the gate grounds `claims[]` only and the renderer writes only the
grounded, scanned claims to `personal/output/`, no personal datum can reach a
shareable artifact. Never place any PII in `claims[].text`, `quote`, or
`citations`.

## The abstention rule — abstain, never confabulate

When `search` returns zero hits, only leaky (per-country) relpaths, or an
unresolvable / degenerate chunk (empty or a vacuous span), the agent emits an
`abstentions[]` entry and **zero claims** for that element. Each abstention entry
is an **object** `{"text": "<plain-language non-answer>", "reason": "not_in_corpus"}`
— the same shape the conformance fixture uses (the `text` is a human note, the
`reason` is the machine code). It NEVER fabricates a claim or a quote. The honesty
boundary is enforced by the gate: a confabulated quote yields `verdict:"fail"`,
`reasons:["quote_not_in_chunk"]`, exit `1`, and writes nothing.

## The "no inlined volatile values" rule

Never write a dollar amount, a validity window, a settlement-funds figure, or
any requirement text directly into `prose` or into an agent body. IRCC changes
these and an inlined value rots and lies. **Every** requirement statement must
resolve from the corpus via a citation, with the volatile value quoted verbatim
from the resolving chunk. Any number, date, or window that appears must be a
structural placeholder or a verbatim quoted span — never a hand-typed value.
Likewise, bake the short **query**, not a `chunk_id` (ids drift and fail-close).

## Exit-code table

Agents branch on the **envelope** (`ok` and `error.type`) for behaviour, and may
use the **exit code** as a fast-path signal (per
[`../../crawler/CONTRACT.md`](../../crawler/CONTRACT.md)):

| Exit | Meaning | Agent action |
|---|---|---|
| `0` | Ran OK. For `ground`, `verdict:"pass"`; for `search`, a result (a `--cite` miss is still exit `0`, `found:false`). | Read `result`. |
| `1` | `ground` `verdict:"fail"` (still `ok:true`). Renders / writes nothing. | Read `result.violations`; fix or abstain. |
| `2` | `invalid_input` (bad path/args, empty query, malformed answer, non-string `quote`). | Read `error.message`; fix the input. |
| `3` | `missing_dependency` (a required driver/feature absent). | Install the named extra; read `error.message`. |
| `4` | `internal_error` (unexpected failure). | Read `error.message`; inspect stderr for the traceback. |

## See also

- [`README.md`](README.md) — the additive skill-pack index (every agent).
- [`../../crawler/AGENT_SKILL.md`](../../crawler/AGENT_SKILL.md) — the portable
  pipeline skill this contract mirrors in tone and structure.
- [`../../crawler/CONTRACT.md`](../../crawler/CONTRACT.md) — the canonical,
  versioned JSON contract (envelope, per-command `result` fields, error types,
  exit codes, the invariant).
