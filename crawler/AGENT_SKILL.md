# Agent Skill: Drive the `corpus-crawler` Pipeline

A **portable, CLI-agnostic** skill. It is plain Markdown with no proprietary
front-matter and no dependency on any single agent CLI's tool API. Any agent —
Antigravity, OpenAI Codex, Claude, GitHub Copilot, Gemini, or a plain shell
script — can use it, because everything here is **an ordinary shell command plus
JSON parsing**.

The full machine contract (envelope schema, every field, exit codes, the
stdout/stderr invariant) lives in [`CONTRACT.md`](CONTRACT.md). This skill
teaches you how to *use* that contract end to end.

## What the tool does

`corpus-crawler` builds a clean, citable corpus from authoritative sources by
running a four-stage pipeline: **crawl** a content tree → **apply-verdicts**
(quarantine drop-verdict docs) → **completeness** (re-fetch a sample at full
fidelity to catch silent truncation) → **report** (aggregate everything into a
human-readable `REPORT.md` with an overall pass/fail verdict). See
[`README.md`](README.md) for the full pipeline and QC details.

## How it works for agents

Invoke `corpus-crawler` as an ordinary shell command. To get a machine-readable
result, add the **global `--json` flag before the subcommand**:

```
corpus-crawler --json <subcommand> [args...]
```

The invariant (see [`CONTRACT.md`](CONTRACT.md)):

- **stdout** is exactly **one JSON object** — capture it and `json.loads` it.
- **stderr** is human/progress/log text — surface it as diagnostics; never
  parse it.

Because the entire interface is "a shell command that prints one JSON object",
this skill works from **any** agent CLI by shelling out. There is no proprietary
tooling, MCP server, or per-CLI plugin to install.

Every `--json` response is the same five-key envelope:

```json
{
  "schema_version": "1.0",
  "ok": true,
  "command": "report",
  "result": { "...": "per-command payload" },
  "error": null
}
```

Read `ok` first. If `ok` is `true`, read `result`. If `ok` is `false`, read
`error.type` and `error.message`. `result` field names per command are in
[`CONTRACT.md`](CONTRACT.md).

## Install

Run everything from `<repo-root>` so the `crawler` package imports.

- **Core (lean) install** — enough for `apply-verdicts`, `report`, and reading
  the contract:

  ```bash
  pip install corpus-crawler
  ```

- **With the optional crawl driver** — required for `crawl` and for
  `completeness` (both need `crawl4ai`):

  ```bash
  pip install 'corpus-crawler[crawl]'
  ```

If you run a lean install and call `crawl` (or `completeness`), you get a
machine-readable `missing_dependency` error and exit code `3` — that is your
signal to install the `[crawl]` extra (see the worked example below).

## The four commands

Each takes the global `--json` flag before the subcommand. See
[`CONTRACT.md`](CONTRACT.md) for the full `result` schema of each.

| Command | Purpose | Key flags |
|---|---|---|
| `crawl` | Deep-crawl a content tree into a corpus. **Needs `[crawl]`.** | `--seed <seed-url>` (req), `--out <corpus-dir>` (req), `--depth`, `--max-pages`, `--profile`, `--source-type`, `--include`, `--label` |
| `apply-verdicts` | Quarantine `drop`-verdict docs out of the live corpus. | `<corpus-dir>` (positional), `--dry-run` |
| `completeness` | Re-fetch a sample at full fidelity to catch truncation. **Needs `[crawl]`.** | `<corpus-dir>` (positional), `--fraction` (default `0.1`) |
| `report` | Aggregate stats/evals/completeness into `REPORT.md`. | `<corpus-dir>` (positional) |

## Worked examples

### 1. Crawl, then read `result.recorded`

```bash
corpus-crawler --json crawl \
  --seed "<seed-url>" --out "<corpus-dir>" --include "*topic*" \
  | python -c "import json,sys; d=json.load(sys.stdin); \
print('recorded' if d['ok'] else 'error', d['result']['recorded'] if d['ok'] else d['error']['type'])"
```

On a lean install (no `[crawl]`), the same command prints an `ok:false`
envelope with `error.type == "missing_dependency"` and exits `3` — handle that
as in example 3.

### 2. Completeness, then report — branch on `result.verdict`

```bash
# Re-fetch ~10% of live docs at full fidelity (needs the [crawl] extra).
corpus-crawler --json completeness "<corpus-dir>" --fraction 0.1 \
  | python -c "import json,sys; d=json.load(sys.stdin); print('sampled', d['result']['sampled'], 'of', d['result']['total_live'])"

# Aggregate into REPORT.md and read the overall verdict.
corpus-crawler --json report "<corpus-dir>" \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['result']['verdict'])"
```

`report` always returns `ok:true`. The exit code is a coarse pass / not-pass
signal (exit `0` = `pass`, exit `1` = **not** `pass`); **always** read
`result.verdict` for the precise outcome:

- `"pass"` → exit code `0`; the corpus is good.
- `"fail"` → exit code `1`; some docs failed evals (this is a *verdict* fail,
  **not** an execution error — `ok` stays `true`, `error` stays `null`).
- `"incomplete"` → **also exit code `1`**; the completeness audit has not
  confirmed the sample (or flagged truncated docs). Exit `1` therefore covers
  both `fail` and `incomplete`, so branch on `result.verdict`, not the exit code.

A tiny parse pattern you can reuse anywhere:

```bash
corpus-crawler --json report "<corpus-dir>" \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['result']['verdict'])"
```

### 3. Handle the missing-dependency case

```bash
out=$(corpus-crawler --json crawl --seed "<seed-url>" --out "<corpus-dir>")
code=$?
echo "$out" | python -c "
import json, sys
d = json.load(sys.stdin)
if not d['ok'] and d['error']['type'] == 'missing_dependency':
    print(\"Install the crawl extra: pip install 'corpus-crawler[crawl]'\")
    sys.exit(0)
print('recorded', d['result']['recorded'])
"
# Or, as a fast path: exit code 3 means exactly 'install the crawl extra'.
[ "$code" -eq 3 ] && echo "(exit 3 = missing crawl driver)"
```

## Exit-code handling

Agents should branch on the **envelope** (`ok` and `error.type`) for behaviour,
and may use the **exit code** as a fast-path signal. Per
[`CONTRACT.md`](CONTRACT.md):

| Exit | Meaning | Agent action |
|---|---|---|
| `0` | Ran OK (for `report`, verdict `pass`). | Read `result`. |
| `1` | `report` verdict **not `pass`** — `fail` or `incomplete` (still `ok:true`). | Read `result.verdict` for the precise outcome; surface failing/unchecked docs. |
| `2` | `invalid_input` (bad/missing corpus dir, nothing to sample). | Fix the path/args; read `error.message`. |
| `3` | `missing_dependency` (`crawl4ai` absent). | Install the crawl extra: `pip install 'corpus-crawler[crawl]'`. |
| `4` | `internal_error` (unexpected failure, e.g. corrupt corpus JSON). | Read `error.message`; inspect stderr for the traceback. |

## See also

- [`CONTRACT.md`](CONTRACT.md) — the canonical, versioned JSON contract
  (envelope, per-command `result` fields, error types, exit codes, invariant).
- [`README.md`](README.md) — the full human pipeline, QC runbook, and output
  layout.
