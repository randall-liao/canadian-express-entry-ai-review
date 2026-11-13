# Corpus Pipeline Runbook — crawl → QC → enforce → apply verdicts → completeness → report

A **repeatable runbook**. A fresh session with no prior context can follow it
top-to-bottom to build a clean, grounded corpus from **any authoritative source**.
It includes the exact **sub-agent prompt templates** to dispatch.

```
deepcrawl ─▶ QC sub-agents ─▶ verbatim check ─▶ eval_runner ─▶ apply_verdicts ─▶ completeness ─▶ report
 (crawl)     (prune+evals)     (0 rewrites)       (enforce)      (drop stubs)     (re-fetch 10%)  (REPORT.md)
```

Corpus purpose: fill in `<CORPUS_PURPOSE>` — one sentence describing what the
corpus grounds. Only purpose-relevant, authoritative, verbatim-accurate content
belongs in the corpus.

> **Example (built-in `ircc` profile).** `<CORPUS_PURPOSE>` = "ground a multi-agent
> assistant for a *post-ITA Canadian Express Entry permanent-residence (PR) applicant*
> assembling their e-APR." In that instantiation only PR-relevant content is kept.

### Parameters to fill per run

| Placeholder | Meaning | Example (built-in `ircc` profile) |
|---|---|---|
| `<SEED_URL>` | Page to start the deep-crawl from | a `standard-requirements/*.html` page |
| `<INCLUDE_GLOB>` | Keeps BFS inside the seed's subtree | `*medical*`, `*express-entry*`, `*language*` |
| `<OUT_DIR>` | Per-source output directory | `trial/corpus_new/pdi` |
| `<SOURCE_TYPE>` | Corpus source tag | `pdi`, `guidance`, `legislation` |
| `<DOMAIN>` | One phrase naming the tree's topic, used in the QC prompt | `medical requirements/admissibility`, `language testing`, `proof of funds` |
| `<CORPUS_PURPOSE>` | One sentence: what the corpus grounds, used in the QC prompt | ground an assistant for a post-ITA Canadian Express Entry PR applicant assembling their e-APR |
| `<OUT_OF_SCOPE_TOPICS>` | Comma-separated topic families to prune, used in the QC prompt | refugees, protected persons, asylum, temporary residents, visitors, study/work permits, family-class sponsorship, citizenship, enforcement/removal |

---

## 0. Environment (CRITICAL — read first)

- Install the `corpus-crawler` package with a standard documented install (Poetry / pip).
  Drive the pipeline through the `corpus-crawler` console command, or invoke the modules
  with `python -m crawler.*` where no console subcommand exists (eval enforcement).
- **The one crawl4ai story.** Crawl steps require the optional `crawl` extra (crawl4ai +
  headless Chromium): `pip install 'corpus-crawler[crawl]'` (or, in a Poetry checkout,
  `poetry install --extras crawl`).
- The lean core install runs eval enforcement, `apply-verdicts`, and `report`. Only the
  `crawl` step and `completeness --fetch` need the `[crawl]` extra.
- Run all `crawler.*` modules **from the repo root** so the `crawler` package imports.

---

## 1. Choose the seed + scope

Pick ONE content tree and fill the parameter table above. Guidance:

- Many sites have **navigation stubs** (~600 chars) where the real policy/content sits
  1–2 link-hops deeper. `--depth 2` reaches it. Raise depth for deeper trees.
- `--include "<INCLUDE_GLOB>"` is REQUIRED — without it BFS escapes the seed's subtree
  into the rest of the site.
- Out-of-scope page families (your `<OUT_OF_SCOPE_TOPICS>`) are excluded by the ACTIVE
  PROFILE's `exclude_url_patterns` — authored from `crawler/profiles/template.yaml` for
  your own source. The built-in `crawler/profiles/ircc.yaml` is the worked example, where
  the patterns target refugee/temp-resident/study-work/PNP/citizenship/etc. families.

---

## 2. Wipe old outputs + crawl

```bash
cd <repo-root>
rm -rf <OUT_DIR>
# requires your environment with the optional `crawl` extra (pip install 'corpus-crawler[crawl]')
python -m crawler.deepcrawl \
  --seed "<SEED_URL>" \
  --depth 2 --max-pages 25 --include "<INCLUDE_GLOB>" \
  --out <OUT_DIR> --source-type <SOURCE_TYPE>
```

Output: `recorded=N skipped_stub=.. skipped_scope=.. skipped_dup=.. -> <OUT_DIR>` and a
`crawl_stats.json` (consumed by the report). The crawler already strips chrome at
write-time and dedups by normalized URL **and** content hash.

**Snapshot pre-QC** (used by the verbatim-safety check in §4):

```bash
rm -rf /tmp/pre_qc_snapshot && cp -r <OUT_DIR> /tmp/pre_qc_snapshot
```

---

## 3. QC + write evals (Gemini sub-agents)

Partition the crawled `.md` files into 3 disjoint sets (~9 each):

```bash
cd <repo-root>/<OUT_DIR>
ls *.md | awk 'NR%3==0{print>"/tmp/setA"} NR%3==1{print>"/tmp/setB"} NR%3==2{print>"/tmp/setC"}'
cat /tmp/setA; echo ---; cat /tmp/setB; echo ---; cat /tmp/setC
```

Dispatch **3 sub-agents via the `task` tool** (NOT a CLI subprocess), in parallel:
`agent_type: general-purpose`, `model: gemini-3.5-flash`, `mode: background`. Each gets
the §3a prompt with `{FILE_LIST}` = its set and `{CORPUS_PURPOSE}` / `{DOMAIN}` /
`{OUT_OF_SCOPE_TOPICS}` filled. Sub-agents are
**stateless** — the prompt must be self-contained. Collect with `read_agent`.

### 3a. QC sub-agent prompt template

```
You are a quality-control + eval-authoring agent for a RAG corpus.

WORKING DIRECTORY (all files are here, use absolute paths):
<repo-root>/<OUT_DIR>/

CORPUS PURPOSE: {CORPUS_PURPOSE}. These pages are authoritative content about: {DOMAIN}.

YOUR FILE SET (process ONLY these files — do not touch any other file):
{FILE_LIST}

For EACH file:
1. Read it. The top is a YAML frontmatter block delimited by `---` lines (url, title,
   etc.). NEVER modify the frontmatter. The `url:` value is needed for the eval.

2. PRUNE (delete) only whole sections/lines that are OUT OF SCOPE for this corpus:
   content exclusively about {OUT_OF_SCOPE_TOPICS} — when such a section sits inside an
   otherwise-relevant page. Also delete leftover navigation/boilerplate lines. KEEP all
   content relevant to this corpus's purpose and this tree's topic.

3. ⚠ VERBATIM SAFETY — ABSOLUTELY CRITICAL: You may ONLY DELETE whole lines/sections.
   NEVER reword, paraphrase, summarize, re-order, or alter ANY retained text — not
   punctuation, not headings, not regulatory refs like [R30] / [subsection R30(3)] /
   [A38]. Grounding depends on exact byte-for-byte text. If unsure, KEEP it.

4. Write a sibling eval file `<doc>.eval.json` with EXACTLY this schema:
{
  "doc": "<filename>.md",
  "url": "<value from frontmatter url:>",
  "relevance_score": <float 0.0-1.0>,
  "verdict": "keep" | "prune" | "drop",
  "quality_flags": [],   // subset of: "truncated","garbled","duplicate","off-topic"
  "summary": "<one sentence>",
  "must_contain": ["<verbatim substring present AFTER pruning>", ...],   // 2-5 distinctive groundable facts/refs
  "must_not_contain": ["<verbatim substring now ABSENT>", ...],          // [] if nothing pruned
  "grounding_refs": ["R30","A38", ...],
  "notes": "<what you pruned and why, brief>"
}

VERDICT RULES:
- "keep": relevant, deleted nothing.
- "prune": relevant, deleted some out-of-scope/nav sections.
- "drop": pure navigation stub (almost no policy text) OR wholly out of scope. For
  "drop": leave the .md UNCHANGED, set must_contain=[] and must_not_contain=[].

5. SELF-VALIDATE before finishing: every must_contain string MUST be a verbatim,
   case-insensitive substring of the doc body AFTER pruning; every must_not_contain
   MUST be absent. Copy must_contain strings directly from the file. Re-open and
   verify; fix any eval that fails.

When done, output a compact table: filename | verdict | relevance_score | #pruned.
Do not ask questions — execute fully and autonomously.
```

> **Example fill (built-in `ircc` profile).** Instantiate the placeholders above as:
> - `{CORPUS_PURPOSE}` = "Ground a multi-agent assistant that helps a *post-ITA Canadian
>   Express Entry permanent-residence (PR) applicant* assemble their e-APR"
> - `{DOMAIN}` = e.g. `medical requirements/admissibility`
> - `{OUT_OF_SCOPE_TOPICS}` = "refugees, protected persons, asylum claimants, temporary
>   residents, visitors, study/work permit holders, family-class sponsorship, citizenship,
>   enforcement/removal"
>
> For a different source, fill the same three placeholders from your own profile and the
> `<CORPUS_PURPOSE>` / `<OUT_OF_SCOPE_TOPICS>` parameter rows.

### 3b. Verify every agent actually produced its evals

A sub-agent can occasionally fail silently (return no response, write nothing). Always
check that one eval exists per doc before proceeding:

```bash
cd <repo-root>/<OUT_DIR>
bash -c 'echo "md=$(ls *.md|wc -l) eval=$(ls *.eval.json 2>/dev/null|wc -l)"'
```

`eval` must equal `md`. If a set is missing, **re-dispatch only that set** (§3a with its
file list). The `eval_runner` resolves each doc from the eval's `doc` field, so an eval
named `foo.md.eval.json` still works — but counts must still match.

```bash
cd <repo-root>/<OUT_DIR>
bash -c '
viol=0
for f in *.md; do
  added=$(grep -vxF -f /tmp/pre_qc_snapshot/"$f" "$f" | grep -v "^[[:space:]]*$" | wc -l)
  [ "$added" -ne 0 ] && { echo "!! $f: $added altered lines"; viol=$((viol+added)); }
done
echo "total verbatim violations: $viol"'
```

**Gate:** total must be `0`. If not, restore the offending files from
`/tmp/pre_qc_snapshot` and re-run that set.

---

## 5. Enforce evals

```bash
cd <repo-root>
python -m crawler.eval_runner <OUT_DIR>
```

**Gate:** exit 0, `0 failed`.

---

## 6. Apply verdicts (quarantine drops)

```bash
cd <repo-root>
python -m crawler.apply_verdicts <OUT_DIR> --dry-run
python -m crawler.apply_verdicts <OUT_DIR>
```

Drops → `<OUT_DIR>/_dropped/` + `dropped.log.json`. Re-run §5; expect `N-drops` pass.

---

## 7. Completeness audit — did the crawler capture the WHOLE page?

This is the anti-regression guard for the past failure mode (crawler silently
truncating page content). It independently re-fetches ~10% of the live docs at FULL
fidelity and has a Gemini high-thinking agent confirm the recorded file is a complete
copy of the live page.

### 7a. Re-fetch the sample

```bash
cd <repo-root>
# requires your environment with the optional `crawl` extra (pip install 'corpus-crawler[crawl]')
python -m crawler.completeness \
  --fetch <OUT_DIR> --fraction 0.1
```

Writes `<OUT_DIR>/completeness/<slug>.live.md` (unfiltered live capture) + `sample.json`.

> **Trial phase: grade EVERY file.** Use `--fraction 1.0` so all live docs are
> re-fetched and graded (not just a 10% sample) — this is how you prove the whole
> corpus is captured before trusting the pipeline. Drop back to `0.1` for routine
> production runs once the crawler is trusted. With many docs, partition the live set
> across several completeness sub-agents (§7b), each handling a subset.

### 7b. Completeness sub-agent (Gemini high-thinking)

Dispatch ONE `task` sub-agent: `agent_type: general-purpose`,
`model: gemini-3.5-flash`, `mode: background`, with this prompt (fill
`{OUT_OF_SCOPE_TOPICS}` from your parameter row — the `ircc` example fill is the same
out-of-scope list used in §3a). Think carefully — this is the final gate:

```
You are a COMPLETENESS auditor for a RAG corpus. Think carefully and be skeptical.

DIRECTORY: <repo-root>/<OUT_DIR>/completeness/
The file ./sample.json lists "pairs": each has {doc, url, live, check}.

For EACH pair:
1. Read the RECORDED doc  ../<doc>          (what the crawler captured, then QC-pruned)
2. Read the FULL live page ./<live>          (an independent, UNFILTERED re-fetch)
3. Read the doc's eval     ../<doc minus .md>.eval.json   (its must_not_contain + notes
   list content that was INTENTIONALLY pruned — that is NOT missing content).

Decide whether the recorded doc is a COMPLETE copy of the live page's substantive
content. The recorded doc may legitimately be MISSING only: (a) site chrome/nav, and
(b) sections intentionally pruned per the eval (out-of-scope: {OUT_OF_SCOPE_TOPICS}).
ANY other
substantive policy text, paragraph, table, list, heading, or regulatory reference that
appears in the live page but NOT in the recorded doc means the crawler truncated the
page — that is an INCOMPLETE capture and a failure.

Write ./<check> (the pair's "check" filename) as JSON:
{
  "doc": "<doc>",
  "url": "<url>",
  "coverage_verdict": "complete" | "incomplete",
  "explained_by_pruning": true | false,   // true only if every difference is chrome or eval-pruned
  "missing_sections": ["<short live-page heading/phrase absent from the recorded doc>", ...],
  "notes": "<one or two sentences: what is missing, or 'complete capture'>"
}

Be precise: quote the live-page heading/phrase that is missing. If the only
differences are chrome or intentionally-pruned out-of-scope sections, set
coverage_verdict="complete" and explained_by_pruning=true. Output a compact table:
doc | coverage_verdict | explained_by_pruning. Execute fully; do not ask questions.
```

---

## 8. Generate the report

```bash
cd <repo-root>
python -m crawler.completeness --report <OUT_DIR>
```

Writes `<OUT_DIR>/REPORT.md` (human-readable: run config, crawl stats, verdict
breakdown, eval pass/fail, completeness table, overall PASS/FAIL). Exit 0 = PASS.

---

## 9. Hand off for validation

Give the human: `<OUT_DIR>/REPORT.md`, the live `*.md` (+ `.eval.json`), `_dropped/`
(audit log), and `completeness/` (re-fetched copies + checks). The report's overall
line tells them at a glance whether the crawl succeeded.

---

## Worked examples

The pipeline is source-agnostic — the trees below are illustrative instantiations of the
parameter table, not dependencies of this runbook. The built-in `ircc` profile ships
several; any one of them (or your own source) exercises the same steps.

### Reference run — one illustrative example (medical-requirements tree, `ircc` profile)

- `<SEED_URL>` = `.../standard-requirements/medical-requirements.html`
- `<INCLUDE_GLOB>` = `*medical*` · `<OUT_DIR>` = `trial/corpus_new/pdi` ·
  `<SOURCE_TYPE>` = `pdi` · `<DOMAIN>` = `medical requirements/admissibility`
- Result: 27 unique pages (9 out-of-scope, 10 dup collapsed) → 0 verbatim violations →
  evals pass → 2 nav-stubs dropped → 25 live docs.

### Examples of other trees

| Tree | `<INCLUDE_GLOB>` | `<SOURCE_TYPE>` | `<DOMAIN>` |
|---|---|---|---|
| Express Entry guidance | `*express-entry*` | `guidance` | `Express Entry e-APR documents` |
| Language requirements | `*language*` | `pdi` | `language testing & proof` |
| Proof of funds | `*proof-funds*` | `guidance` | `settlement funds proof` |
| IRPA / IRPR | `*regulations*` or `*acts*` | `legislation` | `immigration legislation` |
