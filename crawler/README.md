# corpus-crawler — grounded corpus pipeline

Builds a clean, citable RAG corpus from **any authoritative source**. Point it at a
content tree, and each page is deep-crawled, cleaned at the source, quality-controlled
by an LLM, and gated by deterministic evals so only on-topic, verbatim-accurate content
reaches the corpus.

The tool is **source-agnostic**: what to crawl and what to strip is described by a
crawl *profile* (a small YAML file). A built-in example profile —
`crawler/profiles/ircc.yaml`, which targets IRCC immigration content on canada.ca — ships
as the default so you can see a real configuration, but you target your own source by
authoring your own profile (see [Authoring a site profile](#authoring-a-site-profile)).

```
crawl ──▶ LLM QC sub-agents ──▶ eval_runner ──▶ apply-verdicts ──▶ completeness ──▶ REPORT.md
(crawl)   (prune + write evals)    (enforce)     (drop stubs)      (re-fetch ~10%)   (human report)
```

## Modules

| File | Role |
|---|---|
| `deepcrawl.py` | crawl4ai BFS deep-crawl; cleans chrome at write-time; dedups by URL + content hash; writes one `.md` per page + `manifest.json` + `crawl_stats.json`. Site behavior comes from the active profile. |
| `profile.py` / `profiles/*.yaml` | The crawl profile: domains, URL-exclusion globs, slug substitutions, footer/nav/residual cleanup patterns, and default source labels. Copy `profiles/template.yaml` to target your own source. |
| `eval_runner.py` | Executes the per-doc `<doc>.eval.json` QC contracts (must_contain / must_not_contain / relevance / verdict). Non-zero exit on any failure. |
| `apply_verdicts.py` | Moves `verdict: "drop"` docs into `_dropped/` with an audit log; prunes them from the manifest. |
| `completeness.py` | Re-fetches ~10% of live docs **unfiltered** to detect content the crawler dropped (`--fetch`), then aggregates everything into a human-readable `REPORT.md` (`--report`). |
| `cli.py` | The installed `corpus-crawler` console command (a thin dispatcher over the modules). |
| `QC_RUNBOOK.md` | Step-by-step runbook + the exact LLM sub-agent prompt templates (QC + completeness) for repeating a run in a fresh session. |

## Install

The tool ships as a Poetry-managed package named `corpus-crawler` and exposes a single
console entry point, `corpus-crawler`, that you can run from **any directory** once
installed — you do not edit Python source to use it.

```bash
# From a published artifact:
pip install corpus-crawler

# Or, from a source checkout (installs the console command into the active environment):
poetry install
```

**The one crawl4ai story.** Crawling requires the optional `crawl` extra (crawl4ai plus a
headless Chromium). Install it with:

```bash
pip install 'corpus-crawler[crawl]'
# or, in a Poetry checkout:
poetry install --extras crawl
```

The lean core install (`pip install corpus-crawler`) is enough for `apply-verdicts`, eval
enforcement, and `report`. Only `crawl` and `completeness` (its `--fetch` re-fetch) need
the `[crawl]` extra. If you run a command that needs the crawl driver without it installed,
the CLI prints an actionable install hint to stderr; in `--json` mode it emits an
`error.type == "missing_dependency"` envelope and exits with code `3` — that exit code is
your signal to install the `[crawl]` extra.

## Authoring a site profile

A crawl profile tells the crawler which domain to stay on, which page families to skip, and
how to strip site chrome from each page. To target your own source:

```bash
# 1. Copy the template:
cp crawler/profiles/template.yaml my-source.yaml

# 2. Edit my-source.yaml (see the fields below).

# 3. Point the crawler at it:
corpus-crawler crawl --seed "<seed-url>" --out "<corpus-dir>" --profile my-source.yaml
```

The template is valid and loadable as-is (with neutral placeholder rules) so you get
immediate feedback, then you replace the illustrative examples with rules for your site.
Profile fields:

| Field | Purpose |
|---|---|
| `name` | Short identifier for the profile (lowercase, no spaces). |
| `allowed_domains` | Domains the crawl may follow. Empty → derive the allowed domain from the seed URL. |
| `exclude_url_patterns` | `fnmatch` globs for page families to never record (e.g. `*login*`). |
| `slug_substitutions` | Lowercase `[from, to]` URL rewrites applied before exclusion matching (neutralize a long site slug so topic globs don't match it). |
| `strip_query_params` | Query-string params to drop during URL normalization (collapse `?print=true` variants). |
| `footer_patterns` | Regexes that truncate everything from the first match to end-of-page (page footer chrome). |
| `nav_section_patterns` | Regexes for heading-delimited navigation sections to drop entirely. |
| `residual_line_patterns` | Regexes for stray single-line artifacts to drop wherever they appear. |
| `default_source_type` | Default `source_type` written into each page's front-matter. |
| `default_label` | Default attribution/citation label written into each page's front-matter. |

`--profile` also accepts a built-in profile name. The shipped example/default is `ircc`
(`crawler/profiles/ircc.yaml`), which reproduces the IRCC/canada.ca crawl behavior — read
it as a worked example of a fully-specified profile.

## Running the pipeline

Run the full pipeline with the installed `corpus-crawler` console command. The placeholders
below (`<seed-url>`, `<corpus-dir>`, `--include "*topic*"`, `--source-type <type>`) are what
you fill in for your own source.

### 1. Crawl (needs the `[crawl]` extra)

```bash
corpus-crawler crawl \
  --seed "<seed-url>" \
  --depth 2 --max-pages 25 --include "*topic*" \
  --out "<corpus-dir>" --source-type <type> --profile my-source.yaml
```

`--include` keeps the BFS inside the seed's subtree. Output reports
`recorded=N skipped_stub=.. skipped_scope=.. skipped_dup=.. -> <corpus-dir>`.

> **Example (built-in `ircc` profile).** Crawling the IRCC medical-requirements tree:
> `corpus-crawler crawl --seed "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/publications-manuals/operational-bulletins-manuals/standard-requirements/medical-requirements.html" --depth 2 --max-pages 25 --include "*medical*" --out trial/corpus_new/pdi --source-type pdi`

Snapshot the result before QC if you want to prove QC only deleted text (compare the
post-QC files against this snapshot).

### 2. QC + write evals (LLM sub-agents)

Partition the crawled `.md` files into disjoint sets and dispatch QC sub-agents. Each agent
prunes out-of-scope sections **verbatim-safe** (delete whole sections only, never reword)
and writes a `<doc>.eval.json` contract per file.

> The exact prompt template and partitioning command are in **`QC_RUNBOOK.md`**.

### 3. Enforce evals

Eval enforcement has **no console subcommand** — run it as a module from the repo root:

```bash
python -m crawler.eval_runner "<corpus-dir>"
# optional: --min-relevance 0.5  --json
```

Exit `0` / `0 failed` is required to proceed.

### 4. Apply verdicts

```bash
corpus-crawler apply-verdicts "<corpus-dir>" --dry-run
corpus-crawler apply-verdicts "<corpus-dir>"
```

Then re-run step 3 (expect `N - drops` docs, all passing).

### 5. Completeness audit + report

Guards against the crawler silently truncating page content. Re-fetches ~10% of live docs
at **full fidelity** (needs the `[crawl]` extra) so an LLM sub-agent can confirm each recorded
file is a complete copy of its live page (allowing for intentional pruning).

```bash
# 5a. re-fetch the sample (needs the [crawl] extra)
corpus-crawler completeness "<corpus-dir>" --fraction 0.1

# 5b. dispatch the completeness sub-agent — see QC_RUNBOOK.md for the prompt

# 5c. generate the human-readable report
corpus-crawler report "<corpus-dir>"
```

`REPORT.md` ends with an overall **PASS/FAIL** line a human can read at a glance.

## Interpreting outputs

### Output layout

```
<corpus-dir>/
├── <slug>.md            # cleaned, in-scope page (YAML frontmatter: url/title/source_type/…)
├── <slug>.eval.json     # QC contract: verdict, relevance, must_contain/not_contain, refs
├── manifest.json        # url → {path, title, chars, …} for live docs
├── crawl_stats.json     # seed/depth/include + recorded/skipped counts
├── REPORT.md            # human-readable build report (overall PASS/FAIL)
├── completeness/
│   ├── sample.json            # which docs were sampled
│   ├── <slug>.live.md         # independent full-fidelity re-fetch
│   └── <slug>.check.json      # completeness verdict per sampled doc
└── _dropped/
    ├── <slug>.md/.eval.json   # quarantined drop-verdict pages
    └── dropped.log.json       # audit: doc, url, relevance, flags, reason, timestamp
```

### Verdicts

- **keep** — relevant, nothing removed.
- **prune** — relevant, some out-of-scope/nav sections deleted (verbatim-safe).
- **drop** — pure navigation stub or wholly out of scope; quarantined by `apply-verdicts`.

### Report PASS/FAIL

`report` aggregates crawl stats, eval results, and the completeness audit into `REPORT.md`.
The overall verdict is `pass` (everything passed and the sample is confirmed complete),
`fail` (some docs failed evals), or `incomplete` (the completeness audit has not confirmed
the sample). The console exit code is a coarse signal: `0` for `pass`, `1` for anything else
— read the verdict line in `REPORT.md` (or `result.verdict` in `--json` mode) for the
precise outcome.

## Substantiation screening — scope & limits

The CRS auditor produces a **substantiation screening**, **not legal advice** and
**not a substitute** for a licensed immigration consultant or lawyer. It screens
whether a claimed CRS score is backed by the documents an applicant will submit,
and cites the authoritative source behind each rule. It does **not** decide a
case and makes no eligibility ruling or outcome prediction.

**Narrow `SUBSTANTIATED`.** A factor is marked `SUBSTANTIATED` only under a
narrow, deterministic definition: the required proof is present, the backing
evidence is confirmed and audit-eligible, the confirmed value meets the claimed
threshold, and a corpus-grounded, cited admissibility rule applies — a
deterministic match, nothing more.

**What stays `AT-RISK`.** Everything that needs human judgement stays `AT-RISK`
and requires human or professional review: semantic fit, NOC-duty (job-duty) fit,
document authenticity, and officer discretion are never `SUBSTANTIATED` by this
screening. A stale, expired, or unconfirmed input is `AT-RISK`, never green.

The four verdicts are `SUBSTANTIATED` (the only "green"), `GAP` (required proof
missing or below the claimed threshold), `AT-RISK` (needs human judgement, or a
stale/expired input), and `N/A` (not claimed / not applicable).

See [`SCREENING.md`](../SCREENING.md) for the full release framing and the privacy
model. The whole v4.0 safety conformance suite (SAFE-01..04) runs as a single
release gate:

```bash
.venv/bin/python scripts/run_conformance.py
```

## Driving the pipeline from an agent

Any CLI agent (Antigravity / Codex / Claude / Copilot / Gemini) can drive this pipeline by
shelling out and parsing JSON — no proprietary tooling required. Add the global `--json`
flag **before** any subcommand (`corpus-crawler --json <cmd> …`) to get exactly one
machine-readable JSON object on stdout (human/progress text goes to stderr).

- **[`AGENT_SKILL.md`](AGENT_SKILL.md)** — a portable, CLI-agnostic agent skill: install,
  the four commands, the `--json` contract, and worked parse examples.
- **[`CONTRACT.md`](CONTRACT.md)** — the canonical, versioned JSON contract (envelope
  schema, per-command `result` fields, error types, exit codes, and the
  stdout=JSON / stderr=human invariant).

This README does not restate the full schema — see those two documents for the field-level
contract.

## Publish-safety check

Before sharing this repository publicly, run the publish-safety checker. It is a repeatable,
pure-stdlib (no extra dependencies) scan that any maintainer — or CI later — can run from the
repo root:

```bash
python scripts/check_publish_safe.py
```

It scans **only git-tracked files** for machine-specific absolute paths (home directories,
a project virtualenv, a pinned interpreter), secret patterns (private-key headers, cloud
access keys, assigned credentials), and tracked personal/trial corpora. On a clean tree it
prints a `publish-safe` message and exits `0`; on any violation it prints a
`file:line: category: snippet` report and exits non-zero — making it CI-ready.

To whitelist a legitimate reference, append `# publish-safe: allow` to that line. The
checker excludes the vendored agent-framework directory and self-excludes its own source and
test files (they intentionally contain the very tokens being hunted).

## License & attribution

This project is MIT-licensed. The full text lives in the `LICENSE` file at the
repository root, and is shipped in the package metadata (`pyproject.toml` declares
`license-files = ["LICENSE", "NOTICE"]`), so it travels with the installed package.

The MIT license covers **this software** only. Crawled content (e.g. IRCC pages on
canada.ca, the built-in example source) belongs to its **source publisher**, not this
project. See the `NOTICE` file — also at the repository root and shipped in the package
metadata — for attribution, robots.txt compliance, source Terms-of-Service obligations,
and the non-commercial / personal-use expectation.
