# Substantiation screening — scope, limits, and the release conformance gate

This document is the authoritative release framing for the CRS auditor in this
repository. It is written to be generic and shareable: it contains no personal
data and no machine-specific details.

## What this tool does

The CRS auditor performs a **substantiation screening**. Given a candidate's
claimed Comprehensive Ranking System (CRS) factors and the documents they intend
to submit, it screens **whether each claimed factor is substantiated by
audit-eligible evidence under a corpus-grounded, cited rule** — and it surfaces
and cites the authoritative source (IRCC guidance on canada.ca, the IRPA / IRPR,
and IRCC Program Delivery Instructions) behind every rule it applies.

It is a screening aid. It does **not** decide a case, and it produces no
eligibility ruling and no outcome prediction.

## Not legal advice

This tool's output is a CRS substantiation screening. It is **not legal advice**
and is **not a substitute** for a licensed immigration consultant or lawyer. For
advice about a specific situation, consult a licensed professional. Nothing here
should be read as a promise about an application's result.

## The narrow definition of `SUBSTANTIATED`

A factor is marked `SUBSTANTIATED` only under a narrow, deterministic definition —
**all** of the following must hold:

1. the required proof for the factor is present;
2. the backing evidence is **confirmed** and **audit-eligible** (confirmed or
   corrected, quality-ok, and not stale);
3. the confirmed value **meets the claimed threshold**; and
4. a **corpus-grounded, cited admissibility rule** applies.

This is a deterministic match, nothing more. If any of the four conditions is not
met, the factor is never `SUBSTANTIATED`.

## The four-verdict vocabulary

- **`SUBSTANTIATED`** — the only "green": all four conditions above hold.
- **`GAP`** — required proof is missing, or the confirmed value is below the
  claimed threshold.
- **`AT-RISK`** — the factor needs human judgement, or a confirmed input has gone
  stale / expired / unresolved.
- **`N/A`** — the factor is not claimed or not applicable.

## What stays `AT-RISK` (human review required)

The screening deliberately refuses to "green" anything that requires human or
professional judgement. The following are never `SUBSTANTIATED` by this tool and
require human or professional review:

- **semantic fit** — whether prose evidence actually means what a factor requires;
- **NOC-duty (job-duty) fit** — whether real duties match a claimed occupation;
- **document authenticity** — whether a document is genuine;
- **officer discretion** — the final judgement of an IRCC officer;
- **stale or expired inputs** — anything whose grounding is no longer current.

## Privacy model

All personal data (PII) stays in a **local, git-ignored vault**, structurally
separated from the shareable harness. The evidence-bearing report is written
**only** inside the vault. The public, machine-readable output is PII-light and
carries only corpus citations (`relpath#ordinal`), verdicts, counts, and a
vault-relative report path — never an applicant value and never a vault evidence
pointer. Vault artifacts are unstageable by the project `.gitignore` and flagged
by the publish-safety checker.

## Release conformance gate

The whole v4.0 safety conformance suite — no-false-green (SAFE-01), privacy
containment (SAFE-02), retrieve-what-you-cite (SAFE-03), and screening framing
(SAFE-04) — runs as a single, reproducible release gate:

```bash
.venv/bin/python scripts/run_conformance.py
```

The gate exits non-zero if any SAFE criterion fails. The equivalent marker-based
selector is:

```bash
.venv/bin/python -m pytest -m conformance
```
