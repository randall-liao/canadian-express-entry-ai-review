# `corpus-crawler` JSON Output Contract

This is the **canonical, versioned description** of the machine-readable JSON
output that `corpus-crawler` emits when the global `--json` flag is supplied.
An external agent can shell out to the command and `json.loads(stdout)`
deterministically instead of scraping human text.

The contract is implemented in [`contract.py`](contract.py) (the envelope and
constants) and wired through every subcommand in [`cli.py`](cli.py). This
document describes that implementation **1:1** — if the two ever disagree, the
code is authoritative and this file is the bug.

## The stdout = JSON / stderr = human invariant

The global `--json` flag is parsed **before** the subcommand:

```
corpus-crawler --json <subcommand> [args...]
```

When `--json` is supplied:

- **stdout** contains **exactly one** JSON object (a single `json.dumps(...)`
  line, written with `ensure_ascii=False`, terminated by one `\n` and nothing
  else). `json.loads(stdout)` must succeed.
- **stderr** carries **all** human / progress / log / hint text.

When `--json` is **not** supplied, behaviour is unchanged from the historical
human-readable output: each subcommand prints its own human text to stdout. The
`--json` flag is the only thing that activates the machine contract; it never
changes what the underlying pipeline *does*, only how the outcome is reported.

> An agent should therefore capture **stdout** for parsing and may surface
> **stderr** to the user as diagnostics. Never parse stderr.

## The envelope

Every `--json` invocation emits the same five-key envelope:

```json
{
  "schema_version": "1.0",
  "ok": true,
  "command": "report",
  "result": { "...": "per-command payload" },
  "error": null
}
```

| Key | Type | Meaning |
|---|---|---|
| `schema_version` | string | Envelope schema version. Currently `"1.0"`. |
| `ok` | bool | `true` iff no execution error occurred. **`ok == (error is null)`**. |
| `command` | string | The subcommand that ran: `crawl`, `apply-verdicts`, `completeness`, `report`, `index`, `search`, `ground`, `checklist`, `vault`, or `doctor`. |
| `result` | object \| null | The per-command success payload (tables below). `null` whenever `ok` is `false`. |
| `error` | object \| null | `{ "type": str, "message": str }` whenever `ok` is `false`; otherwise `null`. |

### `schema_version` stability promise

`schema_version` uses `MAJOR.MINOR`. Within a major version:

- **Field names never change** and existing fields are never removed or
  repurposed.
- New fields may be **added** (a minor bump), so agents should read fields by
  name and ignore unknown keys rather than asserting an exact key set.

The major version is bumped **only** on a breaking change to the envelope or to
any per-command `result` shape. The value lives in one place —
`SCHEMA_VERSION` in `contract.py`.

### Success vs. verdict-fail vs. execution error

There are three distinct outcomes; do not conflate them:

1. **Success** — `ok: true`, `result` populated, `error: null`, exit `0`.
2. **Verdict fail** — a `report` run that finds a failing *or* incomplete corpus
   is **not** an execution error. It is `ok: true` with `result.verdict ==
   "fail"` (or `"incomplete"`) and exit `1`. `error` stays `null`. The outcome
   is carried by `result.verdict`, not the envelope; exit `1` means only "not
   `pass`".
3. **Execution error** — `ok: false`, `result: null`, `error` populated, with a
   documented non-zero exit code (see below). Reserved for genuine failures: a
   missing optional dependency or unusable input.

## Per-command `result` fields

### `crawl`

Deep-crawls a content tree (requires the optional `crawl` extra). On success:

| Field | Type | Meaning |
|---|---|---|
| `recorded` | int | Pages written to the corpus. |
| `skipped_stub` | int | Pages skipped as navigation/boilerplate stubs. |
| `skipped_scope` | int | Pages skipped for being out of the include scope. |
| `skipped_dup` | int | Pages skipped as URL/content-hash duplicates. |
| `out` | string | Output corpus directory. |
| `profile` | string | Profile name used (e.g. `ircc`). |
| `seed` | string | The seed URL that was crawled. |

### `apply-verdicts`

Quarantines `drop`-verdict documents out of the live corpus. On success:

| Field | Type | Meaning |
|---|---|---|
| `dropped` | int | Documents moved to `_dropped/`. |
| `kept` | int | Live documents remaining after the drop. |
| `dry_run` | bool | `true` if `--dry-run` was set (nothing was moved). |
| `out` | string | The corpus directory operated on. |

### `completeness`

Samples a fraction of live docs and re-fetches them at full fidelity
(`--fetch` path; `--fraction` defaults to `0.1`). On success:

| Field | Type | Meaning |
|---|---|---|
| `sampled` | int | Documents sampled and re-fetched. |
| `total_live` | int | Total live documents available to sample. |
| `fraction` | float | The sampling fraction applied. |
| `out` | string | Where the re-fetched sample was written. |

### `report`

Aggregates crawl stats, evals, and completeness into `REPORT.md`. On success:

| Field | Type | Meaning |
|---|---|---|
| `verdict` | string | Overall verdict: `"pass"`, `"fail"`, or `"incomplete"`. |
| `out` | string | Path to the generated `REPORT.md`. |
| `recorded` | int | Pages recorded during the crawl. |
| `live_docs` | int | Live documents in the corpus. |
| `passed` | int | Documents that passed their evals. |
| `failed` | int | Documents that failed their evals. |
| `drop` | int | Documents with a `drop` verdict. |
| `incomplete` | int | Documents flagged incomplete by the completeness audit. |

A `report` run always emits `ok: true` (it ran successfully). The pass/fail
signal is in `result.verdict` **and** the exit code: exit `0` when the verdict
is `pass`, and exit `1` when the verdict is **not `pass`** — i.e. either `fail`
or `incomplete`. Because exit `1` conflates those two non-pass verdicts, agents
**must** branch on `result.verdict` for the precise outcome; the exit code is
only a coarse pass / not-pass fast-path signal.

### `index`

Builds/rebuilds the FTS5 keyword index over the clean corpus into a SQLite
database (the `--db` path; default `corpus/index.db`). It is a *build* command:
on success it emits `ok: true` and exits `0`. On success:

| Field | Type | Meaning |
|---|---|---|
| `db` | string | Output SQLite index path that was written. |
| `corpus` | string | Resolved corpus root that was indexed. |
| `docs` | int | Live documents indexed (the live-doc filter set). |
| `chunks` | int | Total chunk rows written to the index. |
| `min_text_len` | int | Length (chars) of the smallest indexed chunk. |
| `max_text_len` | int | Length (chars) of the largest indexed chunk (bounded by the chunker's hard ceiling). |
| `tokenizer` | string | FTS5 tokenizer used (`porter unicode61`). |

Error paths reuse the shared taxonomy below: a missing / non-directory
`corpus_dir` is `invalid_input` (exit `2`); a host whose SQLite was built without
FTS5 fails loud as `missing_dependency` (exit `3`).

### `search`

BM25-searches the FTS5 keyword index (the `--db` path; default `corpus/index.db`),
or — with `--cite <id>` — resolves a single citation id back to its exact chunk. It
is a *read-only* command: on success it emits `ok: true` and exits `0`.

**Ranked search** (`search "<query>"`). The `result` carries:

| Field | Type | Meaning |
|---|---|---|
| `query` | string | The raw query, echoed back. |
| `db` | string | The SQLite index path that was searched. |
| `count` | int | Number of hits returned (`== len(hits)`). |
| `hits` | array | BM25-ranked hits, best-first (each hit's fields below). May be empty. |

Each entry in `hits` is an object:

| Field | Type | Meaning |
|---|---|---|
| `chunk_id` | string | Stable `relpath#ordinal` citation id (the content coordinate — **not** the integer rowid). Resolvable via `--cite`. |
| `source_url` | string | Citation field: the document's source URL (verbatim). |
| `relpath` | string | Citation field: the chunk's corpus-relative path. |
| `title` | string | Citation field: the document title. |
| `section` | string | Citation field: the heading-breadcrumb section. |
| `crawl_date` | string | Citation field: when the document was crawled. |
| `snippet` | string | A highlighted `⟦…⟧` preview window — **display only**, never the quotable span. |
| `score` | number | Raw `bm25` score: negative, more-negative = more relevant; `hits` are sorted ascending (best-first). |

**Citation resolve** (`search --cite <id>`). The `result` carries:

| Field | Type | Meaning |
|---|---|---|
| `found` | bool | `true` iff the id resolved to a live, intact chunk. |
| `chunk_id` | string | The requested chunk id, echoed back. |
| `db` | string | The SQLite index path that was queried. |
| `chunk` | object \| null | The resolved chunk on a hit, else `null`. |

On a hit, `chunk` is an object with `chunk_id`, `relpath`, `source_url`, `title`,
`section`, `crawl_date`, and `text` — where `text` is the **exact verbatim chunk
text** (the quotable span the grounding gate grounds on; not a `snippet`).

An unknown **or** content-drifted (stale) id is **fail-closed**: `ok: true`,
`result.found = false`, `chunk: null`, exit `0`. A miss is **not** an execution
error (it mirrors the `report` verdict-fail rule) — the grounding gate reads
`found` / `chunk` to reject ungrounded or stale citations.

Error paths reuse the shared taxonomy below: an empty / all-punctuation query is
rejected as `invalid_input` (exit `2`) before any `MATCH` runs (never an empty
query); a non-file `--db` is `invalid_input` (exit `2`); a host whose SQLite was
built without FTS5 fails loud as `missing_dependency` (exit `3`, the ranked-search
path only — `--cite` needs no FTS5).

### ground

Fail-closed grounding gate (GND-02). Reads **one** structured answer JSON from
**stdin** and checks ONLY its `claims[]` — `prose`, `basis`, and `abstentions` are
free-form filler and are **never** citation-checked (SC1). The stdin answer shape is:

```json
{
  "question": "…",
  "claims": [{ "id": "c1", "text": "…", "citations": ["relpath#NNN", "…"], "quote": "…" }],
  "basis": ["…"],
  "abstentions": ["…"],
  "prose": "…"
}
```

For each claim the gate resolves every citation id in-process via the index
(`--db`; default `corpus/index.db`) and verifies the verbatim `quote` is a
whitespace/case-normalized substring of a resolving chunk's stored text. A claim
passes iff **at least one** citation BOTH resolves AND contains the quote; otherwise
it contributes a fail-closed reason (`uncited` / `unresolvable` / `quote_not_in_chunk`).

The `result` carries the whole-answer verdict:

| Field | Type | Meaning |
|---|---|---|
| `verdict` | string | `"pass"` iff every claim is grounded, else `"fail"`. |
| `total_claims` | int | Number of `claims[]` inspected. |
| `grounded` | int | Claims that passed. |
| `ungrounded` | int | Claims that failed (`== len(violations)`). |
| `violations` | array | One `{ "id", "reasons", "citations" }` per failing claim (`reasons` ⊆ `uncited`/`unresolvable`/`quote_not_in_chunk`). Empty on a pass. |
| `out` | string | **Pass only** — the `personal/output/…` path the rendered answer was written to. |

**Verdict-fail is NOT an execution error** — exactly like `report`. A grounding
`verdict:"fail"` is `ok:true`, `error: null`, **exit `1`**, and renders / writes
**nothing**. Branch on `result.verdict`, not on `ok`; exit `1` means only "not
grounded".

**Pass → render-then-scan-then-write (RPT-03).** A `verdict:"pass"` answer is
rendered (each claim beside its verbatim quote + resolved citation), the rendered
bytes are scanned with the share-safety checker **before any write**, and only a
clean scan is written — to the git-ignored **`personal/output/`** boundary ONLY
(default `--out-dir personal/output`; an `--out-dir` whose resolved path is not under
a `personal/` segment is refused as `invalid_input` / exit `2`). On success: `ok:true`,
`result.out` set, exit `0`.

**Publish-safety refusal.** If the scan finds any absolute-path / secret hit in the
rendered output, the gate **refuses to write** and returns `ok:false`,
`error.type:"internal_error"`, **exit `4`** — a *reuse* of the existing
`internal_error` code (the exit-code taxonomy is unchanged), deliberately
distinguished by the message `refusing to write answer: N publish-safety
violation(s)`. Agents must branch on `error.type` **and** this message, not the bare
exit code (exit `4` also covers an unexpected escaped exception).

**Honesty boundary.** The gate guarantees citation **resolvability** + **verbatim-quote**
substring presence, **NOT** semantic entailment or faithfulness — it proves the quoted
span exists verbatim in a real, un-drifted indexed chunk, not that the chunk supports
the claim's meaning. Semantic faithfulness (VAL-01/VAL-02) is deferred; a human (or a
later phase) must judge whether the quote actually supports the claim.

Error paths reuse the shared taxonomy below: malformed stdin JSON, a missing-key /
malformed answer, a non-file `--db`, or an out-of-boundary `--out-dir` are all
`invalid_input` (exit `2`); a publish-safety hit is `internal_error` (exit `4`). No
new error type, exit code, or schema bump is introduced — the only additive change is
the `ground` command value and this section.

### checklist

Generates a personalized, fully-cited **Layer-1 document checklist** from a local
profile (CHK-01). Reads `$PR_PERSONAL_DIR/profile.yaml` (or `--profile <dir>`;
default `./personal/`), selects the applicable Layer-1 document items, grounds each
one against the index (`--db`; default `corpus/index.db`), and assembles a Phase-25
answer object — **all profile PII confined to `basis[]`**, never to a claim's
generic text/quote/citation. That answer is then run through the SAME fail-closed
gate as [`ground`](#ground): the verb reuses `ground`'s exact
render-then-scan-then-write trust path, so its `result` shape and exit mapping are
**identical** to `ground` (this reuse is what keeps the contract additive).

The `result` carries the same whole-answer verdict dict as `ground`:

| Field | Type | Meaning |
|---|---|---|
| `verdict` | string | `"pass"` iff every claim is grounded, else `"fail"`. |
| `total_claims` | int | Number of `claims[]` inspected. |
| `grounded` | int | Claims that passed. |
| `ungrounded` | int | Claims that failed (`== len(violations)`). |
| `violations` | array | One `{ "id", "reasons", "citations" }` per failing claim. Empty on a pass. |
| `out` | string | **Pass only** — the `personal/output/…` path the rendered checklist was written to. |

**Verdict-fail is NOT an execution error** — exactly like `ground` / `report`. A
grounding `verdict:"fail"` is `ok:true`, `error: null`, **exit `1`**, and renders /
writes **nothing**. Branch on `result.verdict`, not on `ok`.

**Pass → render-then-scan-then-write (RPT-03).** A `verdict:"pass"` checklist is
rendered (each claim beside its verbatim quote + resolved citation — claims ONLY,
never `basis[]`, so the rendered bytes are PII-free by construction), the rendered
bytes are scanned with the share-safety checker **before any write** (under a neutral,
never-excluded label), and only a clean scan is written — to the git-ignored
**`personal/output/`** boundary ONLY (default `--out-dir personal/output`; an
`--out-dir` whose resolved path is not equal to or nested under the repo-anchored
`personal/` is refused as `invalid_input` / exit `2`). On success: `ok:true`,
`result.out` set, exit `0`.

**Publish-safety refusal.** If the scan finds any absolute-path / secret hit in the
rendered checklist, the gate **refuses to write** and returns `ok:false`,
`error.type:"internal_error"`, **exit `4`** — a *reuse* of the existing
`internal_error` code (the exit-code taxonomy is unchanged), deliberately
distinguished by the message `refusing to write checklist: N publish-safety
violation(s)`. Agents must branch on `error.type` **and** this message, not the bare
exit code.

**Honesty boundary.** Identical to `ground`: the gate guarantees citation
**resolvability** + **verbatim-quote** substring presence, **NOT** semantic
entailment — a human must judge whether each quoted span actually supports the
requirement. Personalization is claim *selection* (which items apply) plus their
never-rendered `basis[]` reasons; it is never requirement-text mutation.

`--emit-answer` prints the assembled answer JSON to stdout and exits `0` WITHOUT
gating/rendering/writing (composability — pipe straight into `ground`). This output
is the **raw answer object** (keys `question`/`claims`/`basis`/`abstentions`/`prose`),
**not** the five-key envelope. Because stdout is neither publish-safety-scanned nor
confined to `personal/`, the PII-bearing `basis[]` is **redacted to an empty list**
before printing (WR-02) — only the PII-free `question`/`claims[]` (generic labels +
verbatim corpus quotes) and `abstentions`/`prose` are emitted. The `ground` gate
inspects `claims[]` only, so the redacted answer still gates identically.

Error paths reuse the shared taxonomy below: a missing / non-mapping `profile.yaml`,
a non-file `--db`, or an out-of-boundary `--out-dir` are all `invalid_input` (exit
`2`); a publish-safety hit is `internal_error` (exit `4`). No new error type, exit
code, or schema bump is introduced — `schema_version` stays `"1.0"` and the only
additive change is the `checklist` command value and this section.

### vault

Manages the **private candidate vault** (Phase 29 — VAULT-01/02/03). The vault is
a git-ignored, PII-bearing SQLite store (`personal/candidates/<id>/vault.sqlite`)
plus content-addressed raw files under `files/raw/`. It is the PRIVATE counterpart
of the authoritative corpus and is **never citeable as authority** — a candidate
`evidence_id` (`ev_…`) is never a corpus `citation_id` (`relpath#ordinal`).

This is an **additive** command: the five-key envelope and `schema_version`
(`"1.0"`) are unchanged. **Every `vault` `--json` result is PII-LIGHT** — ids,
counts, statuses, and (where relevant) a content-hash prefix ONLY. Original
filenames, absolute paths, and claimed point values NEVER appear on stdout; they
stay inside `vault.sqlite`. Detailed inspection is deferred to the Phase-30
confirmation views under the vault.

Verbs and their `result` shapes:

| Verb | Args | `result` fields |
|---|---|---|
| `vault init` | `[--candidate ID] [--label TEXT]` | `candidate_id`, `vault_kind` (`"candidate"`), `created` (bool) |
| `vault profile set` | `(--factor-file PATH \| --factor-id ID --group G [--points N] [--level L] [--value-json JSON])` `[--candidate ID]` | `candidate_id`, `factor_count` |
| `vault profile show` | `[--candidate ID]` | `candidate_id`, `factor_count`, `ita_round_count`, `document_count`, `groups_present` (list) |
| `vault ita set` | `--round LABEL [--date YYYY-MM-DD] [--program NAME] --cutoff INT [--claimed-score INT]` `[--candidate ID]` | `round_id`, `has_cutoff` (bool), `program` |
| `vault import` | `PATH --doc-type TYPE [--candidate ID] [--mime-type MIME]` | `document_id`, `evidence_id` (`ev_…`), `doc_type`, `status`, `sha256_prefix` (first 12 hex) |
| `vault list` | `[--candidate ID]` | `candidate_id`, `factor_count`, `ita_round_count`, `document_count`, `documents[]` (each `{document_id, evidence_id, doc_type, status}`) |
| `vault extract` | `(--document-id ID \| --doc-type TYPE) [--candidate ID]` | `candidate_id`, `document_id` (or `null` for a batch), `documents`, `pages`, `values_pending`, `quality_counts` (`{ok, scanned, low_text, rotated, password_protected}`) |
| `vault fields` | `[--candidate ID] [--document-id ID] [--status S]` | `candidate_id`, `count`, `fields[]` (each PII-light `{value_id, field_name, confirmation_status, quality_flag, factor_id, stale, audit_eligible}`) |
| `vault confirm` | `--value-id ID --decision {confirm,correct,reject} [--corrected-value JSON] [--note TEXT] [--candidate ID]` | one PII-light field summary `{value_id, field_name, confirmation_status, quality_flag, factor_id, stale, audit_eligible}` |
| `vault audit` | `[--candidate ID] [--factor ID] [--db PATH] [--round ID]` | PII-light `PublicAuditEnvelope`: `run_id`, `factor_id`, `verdicts[]` (each `{factor_id, factor_group, verdict, reason_code, claim_count}`), `claims[]` (each `{claim_text, citation_id, verdict}`), `counts{}`, `private_output_path` (vault-relative) |

**Phase 30 (extraction quarantine) — additive.** `vault extract` renders every
page + reads text (requires the optional `doc-extract` extra) and writes every
proposed field as a **`pending`** value — never audit-eligible until per-field
confirmation. `vault fields` prints the PII-rich human detail (raw value,
normalized value, source page/crop, affected CRS factor, profile claim) to
**stderr only**; the `--json` `result` carries ONLY the PII-light summaries.
`vault confirm` acts on **exactly one** `--value-id` (there is no bulk
"confirm all"). A missing extraction dependency is `missing_dependency` (exit
`3`). The 5-key envelope and `schema_version` (`"1.0"`) are unchanged.

**PII-light guarantee (tested).** `vault import` / `vault list` never emit the
original filename or an absolute path; only the minted `evidence_id`, `doc_type`,
`status`, and a content-hash prefix cross the stdout boundary.

**Phase 32 (CRS auditor slice) — additive.** `vault audit` runs the fail-closed
first-official-language auditor and emits a PII-LIGHT `PublicAuditEnvelope` as the
`result`: a `run_id`, per-factor `verdicts[]` (each `SUBSTANTIATED` / `GAP` /
`AT-RISK` / `N/A`), generic corpus-cited `claims[]` (each carrying only a corpus
`citation_id` of `relpath#ordinal` shape — NEVER an `ev_` pointer), aggregate
`counts{}`, and the vault-RELATIVE `private_output_path`. The result carries **NO
applicant values and NO `ev_` evidence pointers** — those live only in the
vault-only report written under `candidates/<id>/output/crs-audit/<run_id>.{json,md}`.
Human factor-card detail (applicant values) prints to **stderr only**. A grounded
`GAP`/`AT-RISK`/`N/A` verdict is `ok:true` (a valid result, per the verdict-not-
error rule); a grounding/system failure is `ok:false` with an `invalid_input`
error object and exit `2`, and writes **no report** (SC5). The audit report is a
**vault-only artifact** covered by the publish-safe `VAULT_ARTIFACT` category
(`output/crs-audit/` + `.json`/`.md`). The 5-key envelope, `schema_version`
(`"1.0"`), and the `command` allow-list (reused `command: "vault"`) are unchanged.

**Error paths.** A missing factor/import file, a bad candidate slug, a
containment (`..`/symlink) escape, or invalid inline JSON are all `invalid_input`
(exit `2`). Handlers never interpolate file contents or OS exception snippets into
the envelope (PII boundary). No new error type, exit code, or schema bump is
introduced — the only additive change is the `vault` command value and this
section.

## doctor

Reports the **extraction dependency + scan-quality preflight** (Phase 30 —
EXTRACT-05). It is a **top-level** command (peer of `vault`), used to diagnose a
missing extraction stack or per-document scan-quality problems instead of failing
silently. **Additive**: the five-key envelope and `schema_version` (`"1.0"`) are
unchanged. The `--json` `result` is **PII-light** (package names / booleans /
counts only).

| Command | Args | `result` fields |
|---|---|---|
| `doctor` | `[--candidate ID] [--document-id ID]` | `overall` (`"ok"` \| `"missing_dependency"`), `deps[]` (required: each `{name, required, present, hint}`), `optional[]` (OCR: `pytesseract` wrapper + `tesseract` binary), `quality_counts` (`{pages, scanned, low_text, rotated, password_protected}` when `--candidate`/`--document-id` given, else `null`) |

**Required vs optional.** `pypdfium2`, `Pillow`, and `pdfminer.six` (the
`doc-extract` extra) are **required**: if any is absent, `overall` is
`missing_dependency`, the envelope is `ok:false` with
`error.type == "missing_dependency"`, and the exit code is **`3`** (never
`internal_error`). The optional OCR stack (`pytesseract` + a local `tesseract`
binary) being absent is a **reported warning** — it never fails the command.
Human dependency hints and scan-quality lines go to **stderr**; scan-quality
problems are surfaced but do not by themselves change the exit code.

## Error object + types

On an execution error the envelope sets `ok: false`, `result: null`, and:

```json
{ "type": "missing_dependency", "message": "<human-readable explanation>" }
```

| `error.type` | When it occurs |
|---|---|
| `missing_dependency` | The optional crawl driver (`crawl4ai`) is not installed. Raised by `crawl`, and by `completeness` when it tries to re-fetch. The fix is to install the crawl extra: `pip install 'corpus-crawler[crawl]'`. Also raised by `index` (and by the ranked-search path of `search`) when the host SQLite was built without FTS5 (the fix is a SQLite build with FTS5 enabled). Also raised by `vault extract` and `doctor` when the required `doc-extract` extraction stack (`pypdfium2`/`Pillow`/`pdfminer.six`) is absent — the fix is `pip install 'corpus-crawler[doc-extract]'`. |
| `invalid_input` | Caller-supplied input is unusable: the corpus directory is missing / not a directory, or there are no live docs to sample. For `search`: an empty / all-punctuation query (rejected before any `MATCH`), or a `--db` that is not a file. |
| `internal_error` | A last-resort bucket for any **unexpected** failure that escapes the compute layer in `--json` mode (e.g. a corrupt JSON file inside the corpus, such as a malformed `crawl_stats.json` or `_dropped/dropped.log.json`). The envelope still parses (`ok:false`, `error.message` is a concise `Type: message` string); the full Python traceback is written to **stderr only**, never to stdout. Agents should treat this as a genuine error and inspect `error.message` / stderr. |

## Exit codes

| Exit | Envelope | Meaning |
|---|---|---|
| `0` | `ok: true` | Ran OK. For `report`, the verdict is `pass`. |
| `1` | `ok: true` | `report` ran fine but the verdict is **not `pass`** (i.e. `fail` *or* `incomplete`). The command did **not** error (`ok` stays `true`, `error` is `null`); the precise verdict is always in `result.verdict`. |
| `2` | `ok: false` | `invalid_input` — bad/missing corpus directory, or no docs to sample. |
| `3` | `ok: false` | `missing_dependency` — `crawl4ai` is absent on a lean install. |
| `4` | `ok: false` | `internal_error` — an unexpected exception escaped the compute layer (e.g. a corrupt corpus JSON file). stdout still carries a parseable `ok:false` envelope; the traceback is on stderr. |

The named non-zero codes are constants in `contract.py`
(`EXIT_INVALID_INPUT = 2`, `EXIT_MISSING_DEPENDENCY = 3`,
`EXIT_INTERNAL_ERROR = 4`). Exit `0`/`1` are the established report codes.

> An agent should branch on **`ok` and `error.type`** for behaviour, and may use
> the exit code as a fast-path signal — in particular, treat exit `3` as
> "install the crawl extra".

## Parse it

```python
import json, subprocess

proc = subprocess.run(
    ["corpus-crawler", "--json", "report", "<corpus-dir>"],
    capture_output=True, text=True,
)
data = json.loads(proc.stdout)          # stdout is exactly one JSON object
assert data["schema_version"] == "1.0"
if data["ok"]:
    print("verdict:", data["result"]["verdict"])
else:
    print("error:", data["error"]["type"], "-", data["error"]["message"])
```

See [`AGENT_SKILL.md`](AGENT_SKILL.md) for a portable, end-to-end agent guide
that drives the whole pipeline against this contract.
