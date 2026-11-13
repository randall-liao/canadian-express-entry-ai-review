# Skill-Transferability Auditor

A **context-light**, portable auditor spec for the skill-transferability slice of
the CRS grid. It links back to the shared [`_contract.md`](_contract.md) and adds
no new trust path — it drives the shipped `vault audit` verb. Read `_contract.md`
first (verdict vocabulary, grounding, the `citation_id` / `evidence_id` split, the
PII boundary).

## What makes this module different

Skill transferability does not read documents directly — it **recombines
already-substantiated core factors**. Each combination reads its two component
core verdicts from the cards decided earlier in the same run, so it runs **after**
the core module.

## The five combinations

- education × first official language
- education × Canadian work
- foreign work × first official language
- foreign work × Canadian work
- certificate of qualification × first official language

Each maps to a grounded registry row that names its component factors and its
tier ladder.

## The dependency rule (the SC5 guarantee)

A combination awards its grounded tier points **only when every component is
`SUBSTANTIATED`**. If a component is a `GAP` or missing, the combination is a
factor-level **`GAP`** (`unmet_component`) — never points on an unproven
component. If a component is `AT-RISK`, the combination is **`AT-RISK`**. Changing
a component (for example, lowering one language ability below the tier) changes
the combination verdict downward — the dependency is live, not decorative.

## The caps

Combination points are clamped to the **grounded** combination and total caps
(the education-combination section, the foreign-work-combination section, and the
overall skill-transferability total). The clamp is applied across combinations in
decision order, so the grounded section and total ceilings hold for the whole
group — never exceeded.

## Driving the audit

```bash
corpus-crawler --json vault audit --factor transfer.education_language --db corpus/index.db
corpus-crawler --json vault audit --all --db corpus/index.db
```

- **stdout** is one PII-light envelope; **stderr** carries applicant detail.
- Parse JSON with `.venv/bin/python` (or `jq`) — **never** bare `python`, and run
  conformance tests with `.venv/bin/python -m pytest` from `<repo-root>`.

## No inlined volatile values

This spec names **no** tier points, cap value, benchmark level, or window. Every
such number lives only in a grounded registry row. Refer to caps generically
("the grounded combination and total caps"). The `no_inlined_volatile_rules` gate
scans this file.

## See also

- [`_contract.md`](_contract.md) — the shared substantiation contract.
