# CRS Auditors — Shared Substantiation Contract

A **portable, CLI-agnostic** contract for the four CRS auditor modules
([`core-human-capital.md`](core-human-capital.md), [`spouse-common-law.md`](spouse-common-law.md),
[`skill-transferability.md`](skill-transferability.md), [`additional-points.md`](additional-points.md)).
It is plain Markdown with no proprietary front-matter and no dependency on any
single agent CLI's tool API. Any agent — Antigravity, OpenAI Codex, Claude,
GitHub Copilot, Gemini, or a plain shell script — can follow it, because every
trust-path step is **an ordinary shell command plus JSON parsing**. This is the
single source of truth each module links back to so they stay thin and behave
identically across CLIs. It mirrors the portable document-agent pattern in
[`../document-agents/_contract.md`](../document-agents/_contract.md).

This contract ships **no new trust-path code**. Every hard guarantee —
resolution, grounding, the fail-closed verdict, the PII boundary — is already
shipped and frozen by the Phase 29–32 primitives (`crawler/searchindex.py`,
`crawler/grounding.py`, `crawler/crs_rules.py`, `crawler/crs_audit.py`,
`crawler/vault.py`, `crawler/auditor.py`). Each module is a **context-light
author** that *drives* the shipped `vault audit` verb; it never re-implements a
primitive and never invents a new trust path.

## Critical environment

Bare `python` is **BROKEN** in this repo (a pyenv-win CRLF shim). Every example
below uses the `corpus-crawler` console script for the verb and `.venv/bin/python`
for JSON parsing — **never** bare `python` and never bare `pytest`. Run
conformance tests with `.venv/bin/python -m pytest`. Run everything from
`<repo-root>` so the `crawler` package imports.

## What an auditor module does

Each module covers one slice of the CRS grid and drives the shipped audit verb:

```
corpus-crawler --json vault audit --factor <factor-id> --db corpus/index.db
corpus-crawler --json vault audit --all --db corpus/index.db
```

- `--factor <id>` audits a single factor; `--all` audits every factor on the
  grid and rolls the substantiated points up against the ITA round cutoff.
- **stdout** is exactly **one** five-key envelope (`schema_version`, `ok`,
  `command`, `result`, `error`); the `result` is the **PII-light**
  `PublicAuditEnvelope` (per-factor verdicts, counts, corpus-cited claims, and
  the vault-relative report path). **Read `ok` first.**
- **stderr** is human/applicant detail — surface it as diagnostics; never parse
  it.

## The four-verdict vocabulary (fail-closed)

Every audited factor returns exactly **one** verdict from a closed set:

| Verdict | Meaning |
|---|---|
| `SUBSTANTIATED` | Proof exists, is audit-eligible, meets the claim, and the rule is grounded + cited — the **only** green verdict. |
| `GAP` | Required proof is missing or below the claimed threshold. |
| `AT-RISK` | Evidence is stale / expired / semantically unresolved, or a dependency is unproven. |
| `N/A` | The factor is not claimed or not applicable. |

`SUBSTANTIATED` is **fail-closed**: pending, low-quality, stale, missing, or
unresolved evidence can never reach green. An unwired factor defaults to
`AT-RISK`, never `SUBSTANTIATED`.

## Grounding-by-construction (the frozen gate is reused, never forked)

Before any verdict, every rule row a factor consumes is fed through the shipped
grounding gate (`crawler.crs_rules.validate_registry` →
`crawler.grounding.check_answer`). A row grounds iff its verbatim quote is a
whitespace/case-normalized substring of the corpus chunk its `citation_id`
resolves to. **Any** ungrounded consumed row — or any consumed documented-gap
row — refuses the whole audit (no partial report). A module never re-implements
resolution, quote normalization, or the gate; it only drives them.

## `citation_id` (corpus) stays separate from `evidence_id` (vault)

Two id namespaces that must never cross:

- **`citation_id`** — a corpus `relpath#ordinal` coordinate proving a *rule* is
  grounded. It is PII-free and may appear in the PII-light public envelope.
- **`evidence_id`** — a private `ev_` pointer to the applicant's *document* in
  the vault. It is PII-adjacent and lives ONLY in the vault report and the
  `factor_verdicts` rows — **never** in the public envelope or on stdout.

The spine attaches both to the private factor card; the public down-projection
carries only `citation_id`s. A module never places an `ev_` id in a claim.

## The PII-tier split (cards are vault-only, stdout is PII-light)

- **Private factor cards** (claimed value, confirmed extracted value,
  substantiated points, score delta, evidence pointer, rule citation) are
  **PII-rich** and are written ONLY under the candidate vault
  (`candidates/<id>/output/crs-audit/`). They may carry applicant values because
  they never leave the vault.
- **The public envelope** carries verdicts, counts, corpus `citation_id`s, and a
  vault-relative report path — **never** an applicant value, **never** an `ev_`
  id, **never** an absolute path.

## Score gap vs the ITA cutoff — arithmetic, not advice

`--all` compares the substantiated total against the ITA round cutoff and reports
the **arithmetic** score gap (delta + meets / does not meet). It is a
substantiation screen, **not** an eligibility ruling and **not** legal advice.

## The "no inlined volatile values" rule

Never write a benchmark level, a points value, a cap, a validity window, or a
policy date into this contract, a module body, or a decider. Every such value
lives ONLY in a grounded registry row, paired with a resolving citation and a
verbatim quote. The static `no_inlined_volatile_rules` gate scans
`skills/crs-auditors/**` and `crawler/auditors/` — an inlined threshold trips it.
Refer to thresholds generically (e.g. "the grounded benchmark", "the grounded
combination caps").

## See also

- [`../document-agents/_contract.md`](../document-agents/_contract.md) — the
  portable document-agent contract this one mirrors.
- [`../../crawler/CONTRACT.md`](../../crawler/CONTRACT.md) — the canonical JSON
  envelope, per-command `result` fields, error types, and exit codes.
