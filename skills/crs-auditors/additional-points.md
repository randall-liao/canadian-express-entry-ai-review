# Additional-Points Auditor

A **context-light**, portable auditor spec for the additional-points slice of the
CRS grid. It links back to the shared [`_contract.md`](_contract.md) and adds no
new trust path — it drives the shipped `vault audit` verb. Read `_contract.md`
first (verdict vocabulary, grounding, the `citation_id` / `evidence_id` split, the
PII boundary).

This module is a **substantiation screen, not an eligibility ruling and not legal
advice.** It reports which additional-points claims are grounded and confirmed; it
does not decide admissibility.

## The five factors

- **provincial / territorial nomination** — the grounded maximum, awarded **only**
  when a verified, non-revoked, non-expired nomination is confirmed; otherwise
  `GAP` / `AT-RISK`.
- **arranged employment (job offer)** — see the trap below.
- **Canadian post-secondary study** — an eligible credential length maps to the
  grounded study tier; a secondary / ineligible credential is `GAP`.
- **strong French** — all four French abilities convert (NCLC) and meet the claim
  for the grounded French award; a further English tier can unlock the higher
  grounded total; below threshold → `GAP`.
- **sibling in Canada** — the grounded points on a confirmed relationship +
  citizen/PR status + current-residence chain.

## The arranged-employment (job-offer) trap

A job offer no longer gives CRS additional points under current policy. This
module treats **any** non-zero arranged-employment additional-CRS claim as
**`AT-RISK`** — never `SUBSTANTIATED` and never an automatic award. The **only**
exception is a grounded in-window legacy row, and even then the verdict stays
`AT-RISK` and the resolution is **manual** (no auto-award). A valid offer may
still matter for program eligibility — that is a separate question from CRS
additional points.

## Driving the audit

```bash
corpus-crawler --json vault audit --factor additional.nomination --db corpus/index.db
corpus-crawler --json vault audit --all --db corpus/index.db
```

- **stdout** is one PII-light envelope; **stderr** carries applicant detail.
- Parse JSON with `.venv/bin/python` (or `jq`) — **never** bare `python`, and run
  conformance tests with `.venv/bin/python -m pytest` from `<repo-root>`.

## No inlined volatile values

This spec names **no** points value, NCLC level, validity window, or policy date.
Every such number lives only in a grounded registry row. The
`no_inlined_volatile_rules` gate scans this file.

## See also

- [`_contract.md`](_contract.md) — the shared substantiation contract.
