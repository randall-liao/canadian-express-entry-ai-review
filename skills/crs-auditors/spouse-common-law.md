# Spouse / Common-Law Auditor

A **context-light**, portable auditor spec for the spouse / common-law slice of
the CRS grid. It links back to the shared [`_contract.md`](_contract.md) and adds
no new trust path — it drives the shipped `vault audit` verb and lets the frozen
primitives do every hard guarantee. Read `_contract.md` first (verdict vocabulary,
grounding, the `citation_id` / `evidence_id` split, the PII boundary).

## When this module applies

Spouse factors are scored **only** when the profile declares an **accompanying
spouse or common-law partner who is not a Canadian citizen or permanent
resident** (the explicit `spouse.accompanying` profile signal). Otherwise the run
is in **no-spouse mode** and every spouse factor is **`N/A`**. Spouse mode is
never inferred from the mere presence of spouse evidence — stray evidence must
not flip the mode.

## The three factors

- **spouse education** — the accompanying spouse's highest credential (a foreign
  credential needs an in-window ECA), scored on the grounded spouse education
  table.
- **spouse language** — the spouse's official-language results, converted through
  the grounded conversion chart and scored on the grounded spouse points table,
  clamped to the grounded section cap.
- **spouse Canadian work** — the spouse's eligible Canadian work, aggregated
  across documents with no overlap double-count.

## Ownership separation (the SC5 guarantee)

Every spouse factor consumes **only spouse-owned** confirmed evidence — values
linked to the spouse factor id. A principal-owned value (linked to a `core.*`
factor) is **never** visible to a spouse decider, so it can never substantiate a
spouse factor. A spouse factor claimed with only principal-owned evidence
surfaces as a factor-level **`GAP`**, never a hidden document pass.

## Driving the audit

```bash
corpus-crawler --json vault audit --factor spouse.language --db corpus/index.db
corpus-crawler --json vault audit --all --db corpus/index.db
```

- **stdout** is one PII-light envelope; **stderr** carries applicant detail.
- Parse JSON with `.venv/bin/python` (or `jq`) — **never** bare `python`, and run
  conformance tests with `.venv/bin/python -m pytest` from `<repo-root>`.
- `citation_id` (corpus) stays separate from `evidence_id` (vault); factor cards
  are vault-only, stdout stays PII-light.

## No inlined volatile values

This spec names **no** benchmark level, points value, section cap, validity
window, or policy date. Every such value lives only in a grounded registry row.
Refer to thresholds generically ("the grounded spouse table", "the grounded
section cap"). The `no_inlined_volatile_rules` gate scans this file.

## See also

- [`_contract.md`](_contract.md) — the shared substantiation contract.
